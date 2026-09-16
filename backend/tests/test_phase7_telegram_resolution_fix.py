import pytest
import pytest_asyncio
import uuid
from datetime import datetime, timezone
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
from app.telegram.parser import parse_message
from app.telegram.models import TelegramMessageType, TradeSignal
from app.market_data.instrument_resolver import InstrumentResolver
from app.trading.trade_manager import TradeManager
from app.brokers.paper import PaperBroker
from app.brokers.kotak_neo import KotakNeoBroker

TEST_DB_URL = "sqlite+aiosqlite:///:memory:"

@pytest_asyncio.fixture
async def db_engine():
    engine = create_async_engine(TEST_DB_URL, echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()

@pytest_asyncio.fixture
async def db_session(db_engine):
    async_session = sessionmaker(db_engine, class_=AsyncSession, expire_on_commit=False)
    async with async_session() as session:
        u = User(username="telegram_tester", email="telegram@test.com", hashed_password="pwd")
        session.add(u)
        await session.flush()

        b = BrokerAccount(user_id=u.id, broker_name="PAPER", is_paper_trading=True)
        session.add(b)

        s = TradingSettings(
            user_id=u.id,
            is_algo_active=True,
            max_daily_loss=50000.0,
            max_risk_per_trade=10000.0,
            max_trades_per_day=10,
            max_simultaneous_positions=5,
            trailing_enabled=False
        )
        session.add(s)

        ch = TelegramChannel(channel_id="123456789", channel_name="Test Signals", is_selected=True)
        session.add(ch)
        await session.commit()
        yield session

@pytest.mark.asyncio
async def test_01_real_telegram_signal_uses_real_instrument_resolver():
    """1. Real Telegram signal uses real InstrumentResolver."""
    resolver = InstrumentResolver()
    resolver.initialize()
    
    # Query the exact contract from Telegram: NIFTY 23400 PE 2026-09-22
    res = await resolver.resolve_option_contract(
        underlying="NIFTY",
        strike=23400,
        option_type="PE",
        expiry="2026-09-22"
    )
    assert res is not None
    assert res["pSymbol"] == "57002"
    assert res["pTrdSymbol"] == "NIFTY2692223400PE"
    assert res["pExchSeg"] == "nse_fo"
    assert res["lot_size"] == 65

@pytest.mark.asyncio
async def test_02_real_telegram_signal_does_not_use_paper_nifty_fallback():
    """2. Real Telegram signal does not use PAPER_NIFTY fallback."""
    paper_broker = PaperBroker()
    # PaperBroker.resolve_option_contract should query real resolver and NOT return PAPER_NIFTY for NIFTY
    res = await paper_broker.resolve_option_contract("NIFTY", 23400, "PE", "2026-09-22")
    token = str(res.get("pSymbol") or res.get("instrument_token"))
    assert not token.startswith("PAPER_")
    assert token == "57002"

@pytest.mark.asyncio
async def test_03_valid_current_contract_returns_real_psymbol():
    """3. Valid current contract returns real pSymbol."""
    resolver = InstrumentResolver()
    resolver.initialize()
    res = await resolver.resolve_option_contract("NIFTY", 23400, "PE", "2026-09-22")
    assert res["pSymbol"] == "57002"
    assert res["pTrdSymbol"] == "NIFTY2692223400PE"
    assert res["exchange_segment"] == "nse_fo"

@pytest.mark.asyncio
async def test_04_invalid_contract_is_rejected():
    """4. Invalid contract is rejected (no PAPER_ fallback)."""
    paper_broker = PaperBroker()
    with pytest.raises(Exception) as exc_info:
        await paper_broker.resolve_option_contract("NIFTY", 999999, "PE", "2026-09-22")
    assert exc_info.value is not None

@pytest.mark.asyncio
async def test_05_real_contract_subscribes_to_real_sfeed():
    """5. Real contract subscribes to REAL SFEED (not PAPER_NIFTY)."""
    mds = MarketDataService()
    mds.sfeed_connected = True
    
    mds.subscribe(
        instrument_token="57002",
        symbol="NIFTY2692223400PE",
        exchange_seg="nse_fo",
        trading_symbol="NIFTY2692223400PE",
        strike=23400.0,
        option_type="PE",
        expiry="2026-09-22",
        feed_type="REAL SFEED"
    )
    sub = mds.subscriptions.get("57002")
    assert sub is not None
    assert sub["feed_type"] == "REAL SFEED"
    assert sub["pTrdSymbol"] == "NIFTY2692223400PE"
    assert not sub["instrument_token"].startswith("PAPER_")

@pytest.mark.asyncio
async def test_06_test_data_is_not_selected_for_real_telegram_flow(db_session):
    """6. TEST DATA is not selected for real Telegram flow."""
    listener = TelegramListenerService()
    msg_text = """NIFTY 23400 PE 22 Sept 26 Expiry
Buy above 256
SL below 240
Tgt above 295
CMP 254"""
    
    result = await listener._process_with_session(
        session=db_session,
        message_id="99001",
        channel_id="123456789",
        text=msg_text,
        sender="tester",
        received_at=datetime.now(timezone.utc)
    )
    
    assert result["status"] == "SUCCESS"
    trade_id = result["trade_id"]
    
    stmt = select(Trade).where(Trade.id == trade_id)
    trade = (await db_session.execute(stmt)).scalar_one()
    
    # Token must be the real pSymbol 57002, NOT PAPER_NIFTY...
    assert trade.instrument_token == "57002"
    assert not trade.instrument_token.startswith("PAPER_")

@pytest.mark.asyncio
async def test_07_telegram_cmp_does_not_trigger_entry(db_session):
    """7. Telegram CMP does not trigger entry."""
    paper_broker = PaperBroker()
    trade_manager = TradeManager(db_session, paper_broker)
    
    sig = TradeSignal(
        raw_text="NIFTY 23400 PE CMP 254",
        underlying="NIFTY",
        strike=Decimal("23400"),
        option_type="PE",
        expiry=datetime(2026, 9, 22).date(),
        entry_trigger=Decimal("256"),
        stop_loss=Decimal("240"),
        target=Decimal("295"),
        telegram_cmp=Decimal("254")
    )
    
    trade = await trade_manager.process_new_signal(
        user_id=1,
        broker_account_id=1,
        signal_data=sig,
        message_id="msg_cmp_test",
        resolved_token="57002"
    )
    
    # Status must remain WAITING_FOR_ENTRY; CMP 254 must not trigger
    assert trade.status == TradeState.WAITING_FOR_ENTRY
    assert trade.entry_price is None

@pytest.mark.asyncio
async def test_08_real_ltp_reaches_trade_manager(db_session):
    """8. Real LTP reaches TradeManager."""
    paper_broker = PaperBroker()
    trade_manager = TradeManager(db_session, paper_broker)
    
    sig = TradeSignal(
        raw_text="NIFTY 23400 PE CMP 254",
        underlying="NIFTY",
        strike=Decimal("23400"),
        option_type="PE",
        expiry=datetime(2026, 9, 22).date(),
        entry_trigger=Decimal("256"),
        stop_loss=Decimal("240"),
        target=Decimal("295"),
        telegram_cmp=Decimal("254")
    )
    
    trade = await trade_manager.process_new_signal(
        user_id=1,
        broker_account_id=1,
        signal_data=sig,
        message_id="msg_ltp_test",
        resolved_token="57002"
    )
    
    # Process market tick with real LTP below trigger: 250.0
    affected = await trade_manager.evaluate_market_prices("57002", 250.0)
    assert len(affected) == 0
    
    stmt = select(Trade).where(Trade.id == trade.id)
    t = (await db_session.execute(stmt)).scalar_one()
    assert t.status == TradeState.WAITING_FOR_ENTRY

@pytest.mark.asyncio
async def test_09_real_ltp_ge_trigger_creates_paper_order(db_session):
    """9. Real LTP >= trigger creates PAPER order."""
    paper_broker = PaperBroker()
    trade_manager = TradeManager(db_session, paper_broker)
    
    sig = TradeSignal(
        raw_text="NIFTY 23400 PE CMP 254",
        underlying="NIFTY",
        strike=Decimal("23400"),
        option_type="PE",
        expiry=datetime(2026, 9, 22).date(),
        entry_trigger=Decimal("256"),
        stop_loss=Decimal("240"),
        target=Decimal("295"),
        telegram_cmp=Decimal("254")
    )
    
    trade = await trade_manager.process_new_signal(
        user_id=1,
        broker_account_id=1,
        signal_data=sig,
        message_id="msg_entry_test",
        resolved_token="57002"
    )
    
    # Process tick >= 256.0 with fresh market data
    market_data_service.update_tick("57002", 257.0, feed_type="REAL SFEED")
    affected = await trade_manager.evaluate_market_prices("57002", 257.0)
    assert len(affected) == 1
    
    stmt = select(Trade).where(Trade.id == trade.id)
    t = (await db_session.execute(stmt)).scalar_one()
    assert t.status == TradeState.POSITION_OPEN
    assert t.entry_price == 257.0
    
    # Order created
    stmt_order = select(Order).where(Order.trade_id == trade.id)
    orders = (await db_session.execute(stmt_order)).scalars().all()
    assert len(orders) == 1
    assert orders[0].order_type == "BUY"
    assert orders[0].price == 257.0

@pytest.mark.asyncio
async def test_10_real_ltp_lt_trigger_remains_waiting_for_entry(db_session):
    """10. Real LTP < trigger remains WAITING_FOR_ENTRY."""
    paper_broker = PaperBroker()
    trade_manager = TradeManager(db_session, paper_broker)
    
    sig = TradeSignal(
        raw_text="NIFTY 23400 PE CMP 254",
        underlying="NIFTY",
        strike=Decimal("23400"),
        option_type="PE",
        expiry=datetime(2026, 9, 22).date(),
        entry_trigger=Decimal("256"),
        stop_loss=Decimal("240"),
        target=Decimal("295"),
        telegram_cmp=Decimal("254")
    )
    
    trade = await trade_manager.process_new_signal(
        user_id=1,
        broker_account_id=1,
        signal_data=sig,
        message_id="msg_waiting_test",
        resolved_token="57002"
    )
    
    market_data_service.update_tick("57002", 255.5, feed_type="REAL SFEED")
    affected = await trade_manager.evaluate_market_prices("57002", 255.5)
    assert len(affected) == 0
    stmt = select(Trade).where(Trade.id == trade.id)
    t = (await db_session.execute(stmt)).scalar_one()
    assert t.status == TradeState.WAITING_FOR_ENTRY
    assert t.entry_price is None

@pytest.mark.asyncio
async def test_11_no_duplicate_trade(db_session):
    """11. No duplicate trade on repeated message."""
    listener = TelegramListenerService()
    msg_text = """NIFTY 23400 PE 22 Sept 26 Expiry
Buy above 256
SL below 240
Tgt above 295
CMP 254"""
    
    res1 = await listener._process_with_session(
        session=db_session,
        message_id="99002",
        channel_id="123456789",
        text=msg_text,
        sender="tester",
        received_at=datetime.now(timezone.utc)
    )
    assert res1["status"] == "SUCCESS"
    
    # Reprocess same message_id
    res2 = await listener._process_with_session(
        session=db_session,
        message_id="99002",
        channel_id="123456789",
        text=msg_text,
        sender="tester",
        received_at=datetime.now(timezone.utc)
    )
    assert res2["status"] == "DUPLICATE"

@pytest.mark.asyncio
async def test_12_live_kotak_place_order_never_called(db_session):
    """12. Live Kotak place_order is never called."""
    with patch.object(KotakNeoBroker, "place_order", new_callable=AsyncMock) as mock_live_order:
        paper_broker = PaperBroker()
        trade_manager = TradeManager(db_session, paper_broker)
        
        sig = TradeSignal(
            raw_text="NIFTY 23400 PE CMP 254",
            underlying="NIFTY",
            strike=Decimal("23400"),
            option_type="PE",
            expiry=datetime(2026, 9, 22).date(),
            entry_trigger=Decimal("256"),
            stop_loss=Decimal("240"),
            target=Decimal("295")
        )
        
        trade = await trade_manager.process_new_signal(
            user_id=1,
            broker_account_id=1,
            signal_data=sig,
            message_id="msg_safety_test",
            resolved_token="57002"
        )
        
        market_data_service.update_tick("57002", 260.0, feed_type="REAL SFEED")
        await trade_manager.evaluate_market_prices("57002", 260.0)
        
        # Verify paper order succeeded but live broker was NEVER touched
        mock_live_order.assert_not_called()
        assert mock_live_order.call_count == 0
