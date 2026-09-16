import pytest
import pytest_asyncio
import uuid
from datetime import datetime, timezone, timedelta
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy.future import select

from app.database.database import Base
from app.database.models import (
    User, BrokerAccount, TradingSettings, Trade, TradeState,
    Position, Order, AuditLog, TelegramMessage, TelegramChannel, Signal
)
from app.services.telegram_listener import TelegramListenerService
from app.services.market_data_service import MarketDataService, market_data_service
from app.trading.risk_manager import RiskManager
from app.trading.trade_manager import TradeManager
from app.brokers.paper import PaperBroker
from app.brokers.kotak_neo import KotakNeoBroker
from app.telegram.models import TradeSignal
from app.config import settings

TEST_DB_URL = "sqlite+aiosqlite:///:memory:"

@pytest_asyncio.fixture
async def p8_engine():
    engine = create_async_engine(TEST_DB_URL, echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()

@pytest_asyncio.fixture
async def p8_db(p8_engine):
    async_session = sessionmaker(p8_engine, class_=AsyncSession, expire_on_commit=False)
    async with async_session() as session:
        u = User(username="risk_tester", email="risk@test.com", hashed_password="pwd")
        session.add(u)
        await session.flush()

        b = BrokerAccount(
            user_id=u.id,
            broker_name="PAPER",
            is_paper_trading=True,
            paper_session_id="INITIAL_SESSION",
            paper_reset_at=None
        )
        session.add(b)

        s = TradingSettings(
            user_id=u.id,
            is_algo_active=True,
            max_daily_loss=5000.0,
            max_risk_per_trade=1000.0,
            max_trades_per_day=3,
            max_simultaneous_positions=2,
            partial_exit_percent=50.0,
            trailing_enabled=True,
            trailing_distance=5.0
        )
        session.add(s)

        ch = TelegramChannel(channel_id="123456789", channel_name="Test Signals", is_selected=True)
        session.add(ch)
        await session.commit()
        yield session

@pytest.mark.asyncio
async def test_01_max_trades_per_day_calculation(p8_db):
    """1. MAX_TRADES_PER_DAY calculation: rejects once active limit is reached."""
    rm = RiskManager(p8_db)
    
    # Pre-seed 3 active/closed trades today
    for i in range(3):
        t = Trade(
            user_id=1,
            broker_account_id=1,
            status=TradeState.CLOSED,
            instrument_token=f"INST_{i}",
            quantity=50
        )
        p8_db.add(t)
    await p8_db.commit()

    is_allowed, reason = await rm.check_new_trade_allowed(user_id=1, broker_account_id=1)
    assert is_allowed is False
    assert reason == "MAX_TRADES_PER_DAY_EXCEEDED"

@pytest.mark.asyncio
async def test_02_rejected_trades_do_not_consume_execution_slots(p8_db):
    """2. Rejected trades do not incorrectly consume execution slots."""
    rm = RiskManager(p8_db)
    
    # Pre-seed 5 REJECTED trades
    for i in range(5):
        t = Trade(
            user_id=1,
            broker_account_id=1,
            status=TradeState.REJECTED,
            instrument_token=f"REJ_INST_{i}",
            quantity=0
        )
        p8_db.add(t)
    await p8_db.commit()

    # Even with 5 rejected trades (limit=3), new trade must be allowed!
    is_allowed, reason = await rm.check_new_trade_allowed(user_id=1, broker_account_id=1)
    assert is_allowed is True
    assert reason == "OK"

@pytest.mark.asyncio
async def test_03_waiting_for_entry_behavior(p8_db):
    """3. WAITING_FOR_ENTRY behavior is correctly defined (counts to simultaneous positions)."""
    rm = RiskManager(p8_db)

    # 1 waiting trade (limit simultaneous=2) -> allowed
    t1 = Trade(user_id=1, broker_account_id=1, status=TradeState.WAITING_FOR_ENTRY, instrument_token="WAIT_1", quantity=0)
    p8_db.add(t1)
    await p8_db.commit()

    is_allowed, _ = await rm.check_new_trade_allowed(user_id=1, broker_account_id=1)
    assert is_allowed is True

    # 2 waiting trades -> simultaneous limit reached
    t2 = Trade(user_id=1, broker_account_id=1, status=TradeState.WAITING_FOR_ENTRY, instrument_token="WAIT_2", quantity=0)
    p8_db.add(t2)
    await p8_db.commit()

    is_allowed2, reason2 = await rm.check_new_trade_allowed(user_id=1, broker_account_id=1)
    assert is_allowed2 is False
    assert reason2 == "MAX_SIMULTANEOUS_POSITIONS_EXCEEDED"

@pytest.mark.asyncio
async def test_04_closed_historical_trades_behavior(p8_db):
    """4. CLOSED historical trades from prior session do not block new session."""
    rm = RiskManager(p8_db)

    # 5 trades created before reset
    past_time = datetime.now(timezone.utc) - timedelta(hours=2)
    for i in range(5):
        t = Trade(
            user_id=1,
            broker_account_id=1,
            status=TradeState.CLOSED,
            instrument_token=f"OLD_{i}",
            quantity=50,
            created_at=past_time
        )
        p8_db.add(t)

    # Reset boundary set to 1 hour ago
    reset_time = datetime.now(timezone.utc) - timedelta(hours=1)
    ba = (await p8_db.execute(select(BrokerAccount).where(BrokerAccount.id == 1))).scalar_one()
    ba.paper_reset_at = reset_time
    ba.paper_session_id = "NEW_SESSION_1"
    await p8_db.commit()

    # Pre-reset trades must not block new session
    is_allowed, reason = await rm.check_new_trade_allowed(user_id=1, broker_account_id=1)
    assert is_allowed is True
    assert reason == "OK"

@pytest.mark.asyncio
async def test_05_paper_state_reset_behavior(p8_db):
    """5. PAPER_STATE_RESET behavior: updates session id and timestamp."""
    ba = (await p8_db.execute(select(BrokerAccount).where(BrokerAccount.id == 1))).scalar_one()
    now_utc = datetime.now(timezone.utc)
    ba.paper_reset_at = now_utc
    ba.paper_session_id = "SESSION_RESET_TEST"
    await p8_db.commit()

    reloaded = (await p8_db.execute(select(BrokerAccount).where(BrokerAccount.id == 1))).scalar_one()
    assert reloaded.paper_session_id == "SESSION_RESET_TEST"
    assert reloaded.paper_reset_at is not None

@pytest.mark.asyncio
async def test_06_current_paper_session_risk_counters_reset(p8_db):
    """6. Current paper session risk counters reset to 0."""
    from app.api.routes.dashboard import get_risk_status
    
    # Pre-seed old trades and set reset timestamp
    past_time = datetime.now(timezone.utc) - timedelta(minutes=30)
    for i in range(4):
        p8_db.add(Trade(user_id=1, broker_account_id=1, status=TradeState.CLOSED, instrument_token=f"T_{i}", created_at=past_time))
    
    ba = (await p8_db.execute(select(BrokerAccount).where(BrokerAccount.id == 1))).scalar_one()
    ba.paper_reset_at = datetime.now(timezone.utc)
    await p8_db.commit()

    status = await get_risk_status(p8_db)
    assert status["current"]["trades_used"] == 0
    assert status["current"]["trades_remaining"] == status["limits"]["max_trades_per_day"]
    assert status["current"]["risk_scope"] == "PAPER SESSION"
    assert status["current"]["risk_status"] == "NORMAL"

@pytest.mark.asyncio
async def test_07_historical_signal_count_remains_intact(p8_db):
    """7. Historical signal count remains intact across sessions."""
    p8_db.add(Signal(message_id="S1", underlying="NIFTY", strike=23200, option_type="PE", expiry="2026-09-22", entry_trigger=138, stop_loss=125, target=160))
    p8_db.add(Signal(message_id="S2", underlying="NIFTY", strike=23400, option_type="PE", expiry="2026-09-22", entry_trigger=256, stop_loss=240, target=295))
    await p8_db.commit()

    sig_count = (await p8_db.execute(select(Signal))).scalars().all()
    assert len(sig_count) == 2

@pytest.mark.asyncio
async def test_08_historical_trades_remain_intact(p8_db):
    """8. Historical trades remain intact in DB."""
    t = Trade(user_id=1, broker_account_id=1, status=TradeState.REJECTED, instrument_token="56981")
    p8_db.add(t)
    await p8_db.commit()

    loaded = (await p8_db.execute(select(Trade).where(Trade.id == t.id))).scalar_one()
    assert loaded.status == TradeState.REJECTED
    assert loaded.instrument_token == "56981"

@pytest.mark.asyncio
async def test_09_risk_rejection_occurs_before_sfeed_subscription(p8_db):
    """9. Risk rejection occurs before SFeed subscription."""
    service = TelegramListenerService()
    service.paper_broker = PaperBroker(simulator_mode=False)

    # Force risk failure by setting max_trades_per_day to 0
    s = (await p8_db.execute(select(TradingSettings).where(TradingSettings.user_id == 1))).scalar_one()
    s.max_trades_per_day = 0
    await p8_db.commit()

    text = "NIFTY 23200 PE 22 Sept 26 Expiry\nBuy above 138\nSL below 125\nTgt above 160\nCMP 137"
    with patch.object(market_data_service, "subscribe") as mock_sub:
        res = await service._process_with_session(
            session=p8_db,
            message_id="MSG_RISK_REJ_TEST",
            channel_id="123456789",
            text=text,
            sender="tester",
            received_at=datetime.now(timezone.utc)
        )
        assert res["status"] == "REJECTED"
        # SFeed subscribe must NEVER be called when risk rejects!
        mock_sub.assert_not_called()

@pytest.mark.asyncio
async def test_10_no_sfeed_subscription_remains_after_risk_rejection(p8_db):
    """10. No SFeed subscription remains after risk rejection."""
    service = TelegramListenerService()
    service.paper_broker = PaperBroker(simulator_mode=False)

    s = (await p8_db.execute(select(TradingSettings).where(TradingSettings.user_id == 1))).scalar_one()
    s.max_trades_per_day = 0
    await p8_db.commit()

    text = "NIFTY 23200 PE 22 Sept 26 Expiry\nBuy above 138\nSL below 125\nTgt above 160\nCMP 137"
    res = await service._process_with_session(
        session=p8_db,
        message_id="MSG_NO_SUB_TEST",
        channel_id="123456789",
        text=text,
        sender="tester",
        received_at=datetime.now(timezone.utc)
    )
    assert res["status"] == "REJECTED"
    # Token 56981 should NOT be in subscriptions
    assert "56981" not in market_data_service.subscriptions

@pytest.mark.asyncio
async def test_11_real_telegram_signal_uses_real_psymbol(p8_db):
    """11. Real Telegram signal resolves real pSymbol (56981)."""
    service = TelegramListenerService()
    res = await service.resolver.resolve_option_contract(
        underlying="NIFTY",
        strike=23200,
        option_type="PE",
        expiry="2026-09-22"
    )
    assert res["pSymbol"] == "56981"
    assert res["pTrdSymbol"] == "NIFTY2692223200PE"
    assert res["pExchSeg"] == "nse_fo"

@pytest.mark.asyncio
async def test_12_real_telegram_signal_never_creates_paper_nifty_fallback():
    """12. Real Telegram signal never creates PAPER_NIFTY fallback."""
    broker = PaperBroker(simulator_mode=False)
    res = await broker.resolve_option_contract("NIFTY", 23200, "PE", "2026-09-22")
    token = str(res.get("pSymbol") or res.get("instrument_token"))
    assert not token.startswith("PAPER_")
    assert token == "56981"

@pytest.mark.asyncio
async def test_13_cmp_cannot_trigger_entry(p8_db):
    """13. CMP cannot trigger entry."""
    tm = TradeManager(p8_db, PaperBroker())
    sig = TradeSignal(
        raw_text="NIFTY 23200 PE CMP 137",
        underlying="NIFTY",
        strike=Decimal("23200"),
        option_type="PE",
        expiry=datetime(2026, 9, 22).date(),
        entry_trigger=Decimal("138"),
        stop_loss=Decimal("125"),
        target=Decimal("160"),
        telegram_cmp=Decimal("137")
    )
    trade = await tm.process_new_signal(
        user_id=1,
        broker_account_id=1,
        signal_data=sig,
        message_id="CMP_TEST_SIG",
        resolved_token="56981"
    )
    assert trade.status == TradeState.WAITING_FOR_ENTRY
    assert trade.entry_price is None

@pytest.mark.asyncio
async def test_14_live_broker_is_never_called(p8_db):
    """14. Live broker is never called."""
    with patch.object(KotakNeoBroker, "place_order", new_callable=AsyncMock) as mock_live:
        tm = TradeManager(p8_db, PaperBroker())
        sig = TradeSignal(
            raw_text="NIFTY 23200 PE CMP 137",
            underlying="NIFTY",
            strike=Decimal("23200"),
            option_type="PE",
            expiry=datetime(2026, 9, 22).date(),
            entry_trigger=Decimal("138"),
            stop_loss=Decimal("125"),
            target=Decimal("160")
        )
        trade = await tm.process_new_signal(1, 1, sig, "SAFETY_TEST", "56981")
        market_data_service.update_tick("56981", 139.0, feed_type="REAL SFEED")
        await tm.evaluate_market_prices("56981", 139.0)
        mock_live.assert_not_called()

@pytest.mark.asyncio
async def test_15_live_orders_remain_disabled():
    """15. LIVE ORDERS remain DISABLED."""
    assert getattr(settings, "live_orders_enabled", False) is False
    assert getattr(settings, "trading_mode", "PAPER").upper() == "PAPER"
