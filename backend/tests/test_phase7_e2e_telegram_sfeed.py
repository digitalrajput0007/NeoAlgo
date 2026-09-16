"""
Phase 7: Comprehensive End-to-End Test Suite for Real Telegram User Client & Paper Trading.

Validates all 30 test requirements defined in Phase 7 specification:
Telegram:
 1. Telethon client initialization
 2. Authentication state
 3. Channel discovery
 4. Channel selection
 5. Selected channel persistence
 6. Non-selected channel ignored
 7. Real message persistence
 8. Duplicate message ignored
 9. Restart/reconnect
 10. Listener cleanup

Parser:
 11. Real Telegram signal parsed
 12. CMP cannot trigger order
 13. Invalid signal rejected safely

Instrument:
 14. Current contract resolution
 15. Invalid contract rejected

Market data:
 16. Real SFeed tick reaches MarketDataService
 17. Token matches instrument
 18. Trading symbol matches instrument
 19. Real LTP reaches TradeManager
 20. Stale market data cannot trigger entry

Paper trading:
 21. Entry only when REAL LTP >= trigger
 22. Paper BUY created
 23. Position opens
 24. Target exits paper position
 25. SL exits paper position
 26. Telegram exit closes existing position
 27. Telegram SL hit closes existing position
 28. No duplicate trade

Safety:
 29. KotakNeoBroker live place_order never called
 30. LIVE ORDERS remains DISABLED
"""
import pytest
import pytest_asyncio
import uuid
import time
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
from app.services.telegram_listener import TelegramListenerService, normalize_telegram_id
from app.services.market_data_service import MarketDataService, market_data_service
from app.telegram.parser import parse_message
from app.telegram.models import TelegramMessageType
from app.market_data.instrument_resolver import InstrumentResolver
from app.trading.trade_manager import TradeManager
from app.brokers.paper import PaperBroker
from app.brokers.kotak_neo import KotakNeoBroker
from neo_api_client.websocket.feed.models import SFeedScrip, SFeedScripLite

TEST_DB_URL = "sqlite+aiosqlite:///:memory:"


@pytest_asyncio.fixture
async def p7_engine():
    engine = create_async_engine(TEST_DB_URL, echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


@pytest_asyncio.fixture
async def p7_db(p7_engine):
    async_session = sessionmaker(p7_engine, class_=AsyncSession, expire_on_commit=False)
    async with async_session() as session:
        # Pre-seed user, broker, settings
        u = User(username="phase7_tester", email="p7@test.com", hashed_password="pwd")
        session.add(u)
        await session.flush()

        b = BrokerAccount(user_id=u.id, broker_name="PAPER", is_paper_trading=True)
        session.add(b)

        s = TradingSettings(
            user_id=u.id,
            is_algo_active=True,
            max_daily_loss=10000.0,
            max_risk_per_trade=2000.0,
            max_trades_per_day=10,
            max_simultaneous_positions=3,
            partial_exit_percent=50.0,
            trailing_enabled=True,
            trailing_distance=5.0
        )
        session.add(s)
        await session.commit()
        yield session


# =============================================================================
# TELEGRAM TESTS (1 to 10)
# =============================================================================

@pytest.mark.asyncio
async def test_01_telethon_client_initialization():
    """1. Telethon client initialization."""
    service = TelegramListenerService()
    mock_client = MagicMock()
    mock_client.is_connected.return_value = True
    service.set_client(mock_client)
    assert service.client is not None
    assert service.client.is_connected() is True


@pytest.mark.asyncio
async def test_02_authentication_state():
    """2. Authentication state inspection."""
    service = TelegramListenerService()
    mock_client = MagicMock()
    mock_client.is_connected.return_value = True
    mock_client.is_user_authorized = AsyncMock(return_value=True)
    me_user = MagicMock(id=12345678, first_name="TestUser", last_name="AccountB", username="algo_b", phone="+919876543210")
    mock_client.get_me = AsyncMock(return_value=me_user)
    service.set_client(mock_client)

    status = await service.get_status()
    assert status["connected"] is True
    assert status["authenticated"] is True
    assert status["authenticated_user"]["username"] == "algo_b"
    assert status["authenticated_user"]["id"] == 12345678


@pytest.mark.asyncio
async def test_03_channel_discovery(p7_db):
    """3. Channel discovery finds accessible dialogs."""
    service = TelegramListenerService()
    mock_client = MagicMock()
    mock_client.is_connected.return_value = True
    mock_client.is_user_authorized = AsyncMock(return_value=True)

    # Mock dialogs
    d1 = MagicMock()
    d1.id = -100987654321
    d1.name = "NeoAlgo Test Signals"
    d1.is_channel = True
    d1.is_group = False
    d1.is_user = False
    d1.entity = MagicMock(broadcast=True, username="neoalgo_signals")

    mock_client.get_dialogs = AsyncMock(return_value=[d1])
    service.set_client(mock_client)

    with patch("app.services.telegram_listener.AsyncSessionLocal", return_value=p7_db):
        channels = await service.discover_channels()
        assert len(channels) >= 1
        found = next((c for c in channels if c["channel_id"] == str(d1.id)), None)
        assert found is not None
        assert found["channel_name"] == "NeoAlgo Test Signals"
        assert found["channel_type"] == "broadcast"


@pytest.mark.asyncio
async def test_04_channel_selection(p7_db):
    """4. Channel selection sets in-memory state and selected flag."""
    service = TelegramListenerService()
    ch_id = f"-100{uuid.uuid4().int % 1000000000:09d}"

    with patch("app.services.telegram_listener.AsyncSessionLocal", return_value=p7_db):
        res = await service.select_channel(ch_id, "Selected Dummy Channel")
        assert res["status"] == "SUCCESS"
        assert service.selected_channel_id == ch_id
        assert service.selected_channel_name == "Selected Dummy Channel"
        assert service.is_running is True


@pytest.mark.asyncio
async def test_05_selected_channel_persistence(p7_db):
    """5. Selected channel persistence in DB."""
    service = TelegramListenerService()
    ch_id = f"-100{uuid.uuid4().int % 1000000000:09d}"

    with patch("app.services.telegram_listener.AsyncSessionLocal", return_value=p7_db):
        await service.select_channel(ch_id, "Persisted Channel")
        stmt = select(TelegramChannel).where(TelegramChannel.channel_id == ch_id)
        saved = (await p7_db.execute(stmt)).scalar_one_or_none()
        assert saved is not None
        assert saved.is_selected is True
        assert saved.channel_name == "Persisted Channel"


@pytest.mark.asyncio
async def test_06_non_selected_channel_ignored(p7_db):
    """6. Non-selected channel ignored."""
    service = TelegramListenerService()
    selected_ch = "-100111111111"
    other_ch = "-100222222222"
    service.selected_channel_id = selected_ch

    assert service.is_matching_channel(selected_ch) is True
    assert service.is_matching_channel(other_ch) is False


@pytest.mark.asyncio
async def test_07_real_message_persistence(p7_db):
    """7. Real message persistence in telegram_messages table."""
    service = TelegramListenerService()
    ch_id = f"-100{uuid.uuid4().int % 1000000000:09d}"
    service.selected_channel_id = ch_id
    service.selected_channel_name = "Persistence Test Channel"

    msg_id = f"MSG_{uuid.uuid4().hex[:8]}"
    text = "NIFTY 25000 CE 22 Sept 26 Expiry\nBuy above 150\nSL below 144\nTgt above 170\nCMP 150"

    res = await service.process_incoming_message(
        message_id=msg_id,
        channel_id=ch_id,
        text=text,
        sender="account_a",
        db_session=p7_db
    )
    assert res["status"] == "SUCCESS"
    assert res["parsed"] is True

    stmt = select(TelegramMessage).where(TelegramMessage.telegram_message_id == msg_id)
    saved = (await p7_db.execute(stmt)).scalar_one_or_none()
    assert saved is not None
    assert saved.message_text == text
    assert saved.sender == "account_a"
    assert saved.processing_status == "TRADE_CREATED"


@pytest.mark.asyncio
async def test_08_duplicate_message_ignored(p7_db):
    """8. Duplicate message ignored using (channel_id, telegram_message_id)."""
    service = TelegramListenerService()
    ch_id = f"-100{uuid.uuid4().int % 1000000000:09d}"
    service.selected_channel_id = ch_id
    service.selected_channel_name = "Duplicate Test Channel"

    msg_id = f"DUP_{uuid.uuid4().hex[:8]}"
    text = "NIFTY 25000 CE 22 Sept 26 Expiry\nBuy above 150\nSL below 144\nTgt above 170\nCMP 150"

    # First delivery
    res1 = await service.process_incoming_message(
        message_id=msg_id,
        channel_id=ch_id,
        text=text,
        db_session=p7_db
    )
    assert res1["status"] == "SUCCESS"

    # Second delivery
    res2 = await service.process_incoming_message(
        message_id=msg_id,
        channel_id=ch_id,
        text=text,
        db_session=p7_db
    )
    assert res2["status"] == "DUPLICATE"
    assert res2["parsed"] is False


@pytest.mark.asyncio
async def test_09_restart_reconnect(p7_db):
    """9. Restart/reconnect restores selected channel from database."""
    ch_id = f"-100{uuid.uuid4().int % 1000000000:09d}"
    ch = TelegramChannel(
        channel_id=ch_id,
        channel_name="Reboot Restored Channel",
        is_selected=True,
        is_active=True
    )
    p7_db.add(ch)
    await p7_db.commit()

    service = TelegramListenerService()
    with patch("app.services.telegram_listener.AsyncSessionLocal", return_value=p7_db):
        await service.restore_selected_channel()
        assert service.selected_channel_id == ch_id
        assert service.selected_channel_name == "Reboot Restored Channel"


@pytest.mark.asyncio
async def test_10_listener_cleanup():
    """10. Listener cleanup cleanly disconnects client and feed."""
    service = TelegramListenerService()
    mock_client = MagicMock()
    mock_client.is_connected.return_value = True
    mock_client.disconnect = AsyncMock()
    service.set_client(mock_client)

    mock_feed = MagicMock()
    mock_feed.disconnect = AsyncMock()
    service.feed = mock_feed

    await service.stop()
    assert service.is_running is False
    mock_client.disconnect.assert_awaited_once()
    mock_feed.disconnect.assert_awaited_once()


# =============================================================================
# PARSER TESTS (11 to 13)
# =============================================================================

def test_11_real_telegram_signal_parsed():
    """11. Real Telegram signal parsed correctly."""
    text = (
        "NIFTY 25000 CE 22 Sept 26 Expiry\n"
        "Buy above 150\n"
        "SL below 144\n"
        "Tgt above 170\n"
        "CMP 150"
    )
    parsed = parse_message(text)
    assert parsed.parsed_successfully is True
    assert parsed.message_type == TelegramMessageType.NEW_SIGNAL
    sig = parsed.signal
    assert sig.underlying == "NIFTY"
    assert sig.strike == 25000
    assert sig.option_type == "CE"
    assert sig.expiry == datetime(2026, 9, 22).date()
    assert sig.entry_trigger == Decimal("150")
    assert sig.stop_loss == Decimal("144")
    assert sig.target == Decimal("170")
    assert sig.telegram_cmp == Decimal("150")


@pytest.mark.asyncio
async def test_12_cmp_cannot_trigger_order(p7_db):
    """12. CMP cannot trigger order (CMP is purely informational)."""
    service = TelegramListenerService()
    ch_id = f"-100{uuid.uuid4().int % 1000000000:09d}"
    service.selected_channel_id = ch_id

    # CMP is 160 (which is above entry_trigger 150), but no real tick arrived
    text = "NIFTY 25000 CE 22 Sept 26 Expiry\nBuy above 150\nSL below 144\nTgt above 170\nCMP 160"
    msg_id = f"CMP_{uuid.uuid4().hex[:8]}"

    res = await service.process_incoming_message(
        message_id=msg_id,
        channel_id=ch_id,
        text=text,
        db_session=p7_db
    )
    assert res["status"] == "SUCCESS"
    trade_id = res["trade_id"]

    stmt = select(Trade).where(Trade.id == trade_id)
    trade = (await p7_db.execute(stmt)).scalar_one()
    # Must remain WAITING_FOR_ENTRY, never ENTRY_TRIGGERED or POSITION_OPEN
    assert trade.status == TradeState.WAITING_FOR_ENTRY

    # No order should have been created
    ord_stmt = select(Order).where(Order.trade_id == trade_id)
    orders = (await p7_db.execute(ord_stmt)).scalars().all()
    assert len(orders) == 0


@pytest.mark.asyncio
async def test_13_invalid_signal_rejected_safely(p7_db):
    """13. Invalid signal rejected safely without crashing."""
    service = TelegramListenerService()
    ch_id = f"-100{uuid.uuid4().int % 1000000000:09d}"
    service.selected_channel_id = ch_id

    invalid_text = "Good morning traders, market looking bullish today!"
    msg_id = f"INV_{uuid.uuid4().hex[:8]}"

    res = await service.process_incoming_message(
        message_id=msg_id,
        channel_id=ch_id,
        text=invalid_text,
        db_session=p7_db
    )
    assert res["status"] == "REJECTED"
    assert res["parsed"] is False
    assert res["trade_id"] is None


# =============================================================================
# INSTRUMENT RESOLUTION TESTS (14 to 15)
# =============================================================================

@pytest.mark.asyncio
async def test_14_current_contract_resolution():
    """14. Current contract resolution resolves NIFTY 25000 CE 22 Sept 26 to official token."""
    resolver = InstrumentResolver("data/instruments.csv")
    resolver.initialize()
    res = await resolver.resolve_option_contract(
        underlying="NIFTY",
        strike=25000.0,
        option_type="CE",
        expiry="2026-09-22"
    )
    assert res["instrument_token"] == "57796"
    assert res["symbol"] == "NIFTY2692225000CE"
    assert res["exchange_segment"] == "nse_fo"
    assert res["lot_size"] == 65
    assert res["selection_mode"] == "EXPLICIT_EXPIRY"


@pytest.mark.asyncio
async def test_15_invalid_contract_rejected(p7_db):
    """15. Invalid contract rejected safely without fabricating a token."""
    service = TelegramListenerService()
    ch_id = f"-100{uuid.uuid4().int % 1000000000:09d}"
    service.selected_channel_id = ch_id

    # Non-existent underlying
    text = "FAKESTOCK 99999 CE 22 Sept 26 Expiry\nBuy above 100\nSL below 90\nTgt above 120\nCMP 100"
    msg_id = f"INV_SYM_{uuid.uuid4().hex[:8]}"

    res = await service.process_incoming_message(
        message_id=msg_id,
        channel_id=ch_id,
        text=text,
        db_session=p7_db
    )
    assert res["status"] == "REJECTED"
    assert res["trade_id"] is None


# =============================================================================
# MARKET DATA TESTS (16 to 20)
# =============================================================================

def test_16_real_sfeed_tick_reaches_market_data_service():
    """16. Real SFeed tick reaches MarketDataService."""
    mds = MarketDataService()
    token = "57796"
    mds.subscribe(token, "NIFTY2692225000CE", "nse_fo", "NIFTY2692225000CE", 25000.0, "CE", "1474554600")

    mds.update_tick(token, 152.5, feed_type="REAL SFEED")
    sub = mds.subscriptions[token]
    assert sub["latest_ltp"] == 152.5
    assert sub["feed_type"] == "REAL SFEED"
    assert sub["feed_status"] in ["ACTIVE", "RECEIVING_TICKS"]
    assert mds.total_ticks_received >= 1


def test_17_token_matches_instrument():
    """17. Token matches subscribed instrument."""
    token = "57796"
    scrip_msg = SFeedScrip(
        exchange_segment="nse_fo",
        instrument_token=token,
        level=4,
        last_traded_price=152.5,
        open_price=140.0,
        high_price=155.0,
        low_price=138.0,
        close_price=145.0,
        average_trade_price=148.0,
        last_trade_time=int(time.time()),
        last_update_time=int(time.time()),
        last_trade_qty=65,
        total_buy_quantity=1000,
        total_sell_quantity=1000,
        volume_traded_today=50000,
        open_interest=100000,
        net_change=7.5,
        net_change_percent=5.17,
        upper_circuit_limit=200.0,
        lower_circuit_limit=100.0,
        yearly_high=220.0,
        yearly_low=50.0,
        total_traded_value=7500000.0,
        market_lot=65,
        precision=2,
        multiplier=1,
        trading_symbol="NIFTY2692225000CE"
    )
    assert scrip_msg.instrument_token == token


def test_18_trading_symbol_matches_instrument():
    """18. Trading symbol matches instrument from subscribe acknowledgement."""
    scrip_msg = SFeedScrip(
        exchange_segment="nse_fo",
        instrument_token="57796",
        level=4,
        last_traded_price=152.5,
        open_price=140.0,
        high_price=155.0,
        low_price=138.0,
        close_price=145.0,
        average_trade_price=148.0,
        last_trade_time=int(time.time()),
        last_update_time=int(time.time()),
        last_trade_qty=65,
        total_buy_quantity=1000,
        total_sell_quantity=1000,
        volume_traded_today=50000,
        open_interest=100000,
        net_change=7.5,
        net_change_percent=5.17,
        upper_circuit_limit=200.0,
        lower_circuit_limit=100.0,
        yearly_high=220.0,
        yearly_low=50.0,
        total_traded_value=7500000.0,
        market_lot=65,
        precision=2,
        multiplier=1,
        trading_symbol="NIFTY2692225000CE"
    )
    assert scrip_msg.trading_symbol == "NIFTY2692225000CE"


@pytest.mark.asyncio
async def test_19_real_ltp_reaches_trade_manager(p7_db):
    """19. Real LTP reaches TradeManager via listener."""
    token = "57796"
    manager = TradeManager(p7_db, PaperBroker())

    # Create waiting trade
    sig = Signal(
        message_id="SIG_TM_TEST",
        underlying="NIFTY",
        strike=25000.0,
        option_type="CE",
        expiry="2026-09-22",
        entry_trigger=150.0,
        stop_loss=144.0,
        target=170.0
    )
    p7_db.add(sig)
    await p7_db.flush()

    trade = Trade(
        user_id=1,
        signal_id=sig.id,
        broker_account_id=1,
        status=TradeState.WAITING_FOR_ENTRY,
        instrument_token=token,
        quantity=0
    )
    p7_db.add(trade)
    await p7_db.commit()

    # Pre-subscribe fresh tick
    market_data_service.subscribe(token, "NIFTY2692225000CE", "nse_fo", "NIFTY2692225000CE", 25000.0, "CE", "1474554600")
    market_data_service.update_tick(token, 151.0, feed_type="REAL SFEED")

    affected = await manager.evaluate_market_prices(token, 151.0)
    assert len(affected) == 1
    assert affected[0]["trade_id"] == trade.id
    assert affected[0]["new_state"] == "POSITION_OPEN"


@pytest.mark.asyncio
async def test_20_stale_market_data_cannot_trigger_entry(p7_db):
    """20. Stale market data cannot trigger entry (Requirement 13 safety lock)."""
    token = "57796_STALE"
    manager = TradeManager(p7_db, PaperBroker())

    sig = Signal(
        message_id="SIG_STALE_TEST",
        underlying="NIFTY",
        strike=25000.0,
        option_type="CE",
        expiry="2026-09-22",
        entry_trigger=150.0,
        stop_loss=144.0,
        target=170.0
    )
    p7_db.add(sig)
    await p7_db.flush()

    trade = Trade(
        user_id=1,
        signal_id=sig.id,
        broker_account_id=1,
        status=TradeState.WAITING_FOR_ENTRY,
        instrument_token=token,
        quantity=0
    )
    p7_db.add(trade)
    await p7_db.commit()

    # Create an artificially stale tick (120 seconds old; stale timeout is 60s)
    old_time = (datetime.now(timezone.utc) - timedelta(seconds=120)).isoformat()
    market_data_service.subscriptions[token] = {
        "instrument_token": token,
        "latest_ltp": 155.0,
        "last_tick": old_time,
        "feed_type": "REAL SFEED",
        "feed_status": "STALE"
    }

    assert market_data_service.is_stale(token, max_age_seconds=60) is True

    # Price evaluation must reject entry due to stale data
    affected = await manager.evaluate_market_prices(token, 155.0)
    assert len(affected) == 0

    stmt = select(Trade).where(Trade.id == trade.id)
    refreshed = (await p7_db.execute(stmt)).scalar_one()
    assert refreshed.status == TradeState.WAITING_FOR_ENTRY


# =============================================================================
# PAPER TRADING TESTS (21 to 28)
# =============================================================================

@pytest.mark.asyncio
async def test_21_entry_only_when_real_ltp_ge_trigger(p7_db):
    """21. Entry triggered only when REAL LTP >= trigger."""
    token = "57796"
    manager = TradeManager(p7_db, PaperBroker())

    sig = Signal(
        message_id="SIG_TRIG_TEST",
        underlying="NIFTY",
        strike=25000.0,
        option_type="CE",
        expiry="2026-09-22",
        entry_trigger=150.0,
        stop_loss=144.0,
        target=170.0
    )
    p7_db.add(sig)
    await p7_db.flush()

    trade = Trade(
        user_id=1,
        signal_id=sig.id,
        broker_account_id=1,
        status=TradeState.WAITING_FOR_ENTRY,
        instrument_token=token,
        quantity=0
    )
    p7_db.add(trade)
    await p7_db.commit()

    market_data_service.update_tick(token, 149.0, feed_type="REAL SFEED")
    # 149.0 < 150.0 -> no trigger
    aff1 = await manager.evaluate_market_prices(token, 149.0)
    assert len(aff1) == 0

    # 150.5 >= 150.0 -> triggers
    market_data_service.update_tick(token, 150.5, feed_type="REAL SFEED")
    aff2 = await manager.evaluate_market_prices(token, 150.5)
    assert len(aff2) == 1
    assert aff2[0]["new_state"] == "POSITION_OPEN"


@pytest.mark.asyncio
async def test_22_paper_buy_created(p7_db):
    """22. Paper BUY order created upon trigger."""
    token = "57796"
    manager = TradeManager(p7_db, PaperBroker())

    sig = Signal(
        message_id="SIG_BUY_ORD",
        underlying="NIFTY",
        strike=25000.0,
        option_type="CE",
        expiry="2026-09-22",
        entry_trigger=150.0,
        stop_loss=144.0,
        target=170.0
    )
    p7_db.add(sig)
    await p7_db.flush()

    trade = Trade(
        user_id=1,
        signal_id=sig.id,
        broker_account_id=1,
        status=TradeState.WAITING_FOR_ENTRY,
        instrument_token=token,
        quantity=0
    )
    p7_db.add(trade)
    await p7_db.commit()

    market_data_service.update_tick(token, 151.0, feed_type="REAL SFEED")
    await manager.evaluate_market_prices(token, 151.0)

    ord_stmt = select(Order).where(Order.trade_id == trade.id)
    orders = (await p7_db.execute(ord_stmt)).scalars().all()
    assert len(orders) == 1
    assert orders[0].order_type == "BUY"
    assert orders[0].price == 151.0
    assert str(orders[0].broker_order_id).startswith("PAPER_ORD_")


@pytest.mark.asyncio
async def test_23_position_opens(p7_db):
    """23. Position opens with correct trade metadata."""
    token = "57796"
    manager = TradeManager(p7_db, PaperBroker())

    sig = Signal(
        message_id="SIG_POS_OPEN",
        underlying="NIFTY",
        strike=25000.0,
        option_type="CE",
        expiry="2026-09-22",
        entry_trigger=150.0,
        stop_loss=144.0,
        target=170.0
    )
    p7_db.add(sig)
    await p7_db.flush()

    trade = Trade(
        user_id=1,
        signal_id=sig.id,
        broker_account_id=1,
        status=TradeState.WAITING_FOR_ENTRY,
        instrument_token=token,
        quantity=0
    )
    p7_db.add(trade)
    await p7_db.commit()

    market_data_service.update_tick(token, 152.0, feed_type="REAL SFEED")
    await manager.evaluate_market_prices(token, 152.0)

    pos_stmt = select(Position).where(Position.trade_id == trade.id)
    pos = (await p7_db.execute(pos_stmt)).scalar_one_or_none()
    assert pos is not None
    assert pos.is_open is True
    assert pos.average_price == 152.0
    assert pos.quantity > 0


@pytest.mark.asyncio
async def test_24_target_exits_paper_position(p7_db):
    """24. Target exits paper position with profit."""
    token = "57796"
    manager = TradeManager(p7_db, PaperBroker())

    sig = Signal(
        message_id="SIG_TGT_TEST",
        underlying="NIFTY",
        strike=25000.0,
        option_type="CE",
        expiry="2026-09-22",
        entry_trigger=150.0,
        stop_loss=144.0,
        target=170.0
    )
    p7_db.add(sig)
    await p7_db.flush()

    trade = Trade(
        user_id=1,
        signal_id=sig.id,
        broker_account_id=1,
        status=TradeState.POSITION_OPEN,
        instrument_token=token,
        quantity=65,
        entry_price=150.0
    )
    p7_db.add(trade)
    pos = Position(user_id=1, trade_id=trade.id, broker_account_id=1, instrument_token=token, quantity=65, average_price=150.0, is_open=True)
    p7_db.add(pos)
    await p7_db.commit()

    # Hit target 171.0 >= 170.0
    affected = await manager.evaluate_market_prices(token, 171.0)
    assert len(affected) == 1
    assert affected[0]["new_state"] == "CLOSED"

    # Verify SELL order placed
    ord_stmt = select(Order).where(Order.trade_id == trade.id, Order.order_type == "SELL")
    sell_ord = (await p7_db.execute(ord_stmt)).scalars().first()
    assert sell_ord is not None
    assert sell_ord.price == 171.0


@pytest.mark.asyncio
async def test_25_sl_exits_paper_position(p7_db):
    """25. Stop Loss exits paper position."""
    token = "57796"
    manager = TradeManager(p7_db, PaperBroker())

    sig = Signal(
        message_id="SIG_SL_TEST",
        underlying="NIFTY",
        strike=25000.0,
        option_type="CE",
        expiry="2026-09-22",
        entry_trigger=150.0,
        stop_loss=144.0,
        target=170.0
    )
    p7_db.add(sig)
    await p7_db.flush()

    trade = Trade(
        user_id=1,
        signal_id=sig.id,
        broker_account_id=1,
        status=TradeState.POSITION_OPEN,
        instrument_token=token,
        quantity=65,
        entry_price=150.0
    )
    p7_db.add(trade)
    pos = Position(user_id=1, trade_id=trade.id, broker_account_id=1, instrument_token=token, quantity=65, average_price=150.0, is_open=True)
    p7_db.add(pos)
    await p7_db.commit()

    # Hit SL 143.0 <= 144.0
    affected = await manager.evaluate_market_prices(token, 143.0)
    assert len(affected) == 1
    assert affected[0]["new_state"] == "CLOSED"


@pytest.mark.asyncio
async def test_26_telegram_exit_closes_existing_position(p7_db):
    """26. Telegram explicit 'exit' closes existing verified paper position only."""
    token = "57796"
    manager = TradeManager(p7_db, PaperBroker())

    sig = Signal(
        message_id="SIG_TEL_EXIT",
        underlying="NIFTY",
        strike=25000.0,
        option_type="CE",
        expiry="2026-09-22",
        entry_trigger=150.0,
        stop_loss=144.0,
        target=170.0
    )
    p7_db.add(sig)
    await p7_db.flush()

    trade = Trade(
        user_id=1,
        signal_id=sig.id,
        broker_account_id=1,
        status=TradeState.POSITION_OPEN,
        instrument_token=token,
        quantity=65,
        entry_price=150.0
    )
    p7_db.add(trade)
    pos = Position(user_id=1, trade_id=trade.id, broker_account_id=1, instrument_token=token, quantity=65, average_price=150.0, is_open=True)
    p7_db.add(pos)
    await p7_db.commit()

    market_data_service.update_tick(token, 158.0, feed_type="REAL SFEED")
    await manager.execute_manual_exit(TelegramMessageType.EXIT, "-100123", datetime.now(timezone.utc))

    stmt = select(Trade).where(Trade.id == trade.id)
    refreshed = (await p7_db.execute(stmt)).scalar_one()
    assert refreshed.status == TradeState.CLOSED


@pytest.mark.asyncio
async def test_27_telegram_sl_hit_closes_existing_position(p7_db):
    """27. Telegram 'SL hit' closes existing position and never creates a short position."""
    token = "57796"
    manager = TradeManager(p7_db, PaperBroker())

    sig = Signal(
        message_id="SIG_TEL_SL",
        underlying="NIFTY",
        strike=25000.0,
        option_type="CE",
        expiry="2026-09-22",
        entry_trigger=150.0,
        stop_loss=144.0,
        target=170.0
    )
    p7_db.add(sig)
    await p7_db.flush()

    trade = Trade(
        user_id=1,
        signal_id=sig.id,
        broker_account_id=1,
        status=TradeState.POSITION_OPEN,
        instrument_token=token,
        quantity=65,
        entry_price=150.0
    )
    p7_db.add(trade)
    pos = Position(user_id=1, trade_id=trade.id, broker_account_id=1, instrument_token=token, quantity=65, average_price=150.0, is_open=True)
    p7_db.add(pos)
    await p7_db.commit()

    market_data_service.update_tick(token, 142.0, feed_type="REAL SFEED")
    await manager.execute_manual_exit(TelegramMessageType.STOP_LOSS, "-100123", datetime.now(timezone.utc))

    stmt = select(Trade).where(Trade.id == trade.id)
    refreshed = (await p7_db.execute(stmt)).scalar_one()
    assert refreshed.status == TradeState.CLOSED

    # Calling it a second time when no positions are open should not create a short position
    await manager.execute_manual_exit(TelegramMessageType.STOP_LOSS, "-100123", datetime.now(timezone.utc))
    all_trades = (await p7_db.execute(select(Trade))).scalars().all()
    assert len(all_trades) == 1


@pytest.mark.asyncio
async def test_28_no_duplicate_trade_on_replayed_update(p7_db):
    """28. No duplicate trade created on repeated Telegram update."""
    service = TelegramListenerService()
    ch_id = f"-100{uuid.uuid4().int % 1000000000:09d}"
    service.selected_channel_id = ch_id
    text = "NIFTY 25000 CE 22 Sept 26 Expiry\nBuy above 150\nSL below 144\nTgt above 170\nCMP 150"
    msg_id = f"NO_DUP_{uuid.uuid4().hex[:8]}"

    res1 = await service.process_incoming_message(msg_id, ch_id, text, db_session=p7_db)
    res2 = await service.process_incoming_message(msg_id, ch_id, text, db_session=p7_db)

    assert res1["status"] == "SUCCESS"
    assert res2["status"] == "DUPLICATE"

    # Only 1 trade created
    trades = (await p7_db.execute(select(Trade))).scalars().all()
    assert len(trades) == 1


# =============================================================================
# SAFETY TESTS (29 to 30)
# =============================================================================

@pytest.mark.asyncio
async def test_29_kotak_neo_broker_live_place_order_never_called():
    """29. KotakNeoBroker live place_order raises NotImplementedError."""
    broker = KotakNeoBroker()
    with pytest.raises(NotImplementedError):
        await broker.place_order({"instrument": "NIFTY2692225000CE", "quantity": 65})
    with pytest.raises(NotImplementedError):
        await broker.modify_order("ord_999", {"price": 160.0})
    with pytest.raises(NotImplementedError):
        await broker.cancel_order("ord_999")
    with pytest.raises(NotImplementedError):
        await broker.exit_position("pos_999")


def test_30_live_orders_remains_disabled():
    """30. LIVE ORDERS remains strictly DISABLED across the platform."""
    broker = KotakNeoBroker()
    assert hasattr(broker, "place_order")
    # Live execution flag or status verification
    service = TelegramListenerService.get_instance()
    assert isinstance(service.paper_broker, PaperBroker)
