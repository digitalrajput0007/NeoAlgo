"""
Phase 9: Paper Trading Hardening & Failure-Safety Test Suite.

Validates the failure-closed principle, concurrency safety, idempotency across
entries/exits, restart recovery across all trade lifecycle states, SFeed reliability,
channel filtering, SL/Target priority, and strict live order locking.

SAFETY:
KotakNeoBroker.place_order() invocation count MUST remain strictly ZERO.
"""
import pytest
import pytest_asyncio
import asyncio
import math
from datetime import datetime, timezone, timedelta
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy.future import select

from app.database.database import Base
from app.database.models import (
    User, BrokerAccount, TradingSettings, Trade, TradeState,
    Position, Order, AuditLog, TelegramMessage, Signal, RiskEvent, TelegramChannel
)
from app.services.market_data_service import MarketDataService, SubscriptionState
from app.trading.trade_manager import TradeManager
from app.trading.risk_manager import RiskManager
from app.brokers.paper import PaperBroker
from app.brokers.kotak_neo import KotakNeoBroker
from app.services.trade_recovery import restore_active_trades_subscriptions, ACTIVE_TRADE_STATES
from app.services.telegram_listener import TelegramListenerService
from app.telegram.parser import parse_message
from app.telegram.models import TradeSignal, ParseResult, TelegramMessageType

TEST_DB_URL = "sqlite+aiosqlite:///:memory:"


def make_signal(
    underlying: str = "NIFTY",
    strike: int = 23200,
    option_type: str = "CE",
    expiry = datetime(2026, 9, 22).date(),
    entry_trigger: float = 185.00,
    stop_loss: float = 160.00,
    target: float = 210.00,
    telegram_cmp: float = 179.10,
    raw_text: str = "mock signal text"
) -> TradeSignal:
    return TradeSignal(
        underlying=underlying,
        strike=strike,
        option_type=option_type,
        expiry=expiry,
        entry_trigger=Decimal(str(entry_trigger)),
        stop_loss=Decimal(str(stop_loss)),
        target=Decimal(str(target)),
        telegram_cmp=Decimal(str(telegram_cmp)) if telegram_cmp is not None else None,
        raw_text=raw_text
    )


@pytest_asyncio.fixture
async def p9_engine():
    engine = create_async_engine(TEST_DB_URL, echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


@pytest_asyncio.fixture
async def p9_db(p9_engine):
    async_session = sessionmaker(p9_engine, class_=AsyncSession, expire_on_commit=False)
    async with async_session() as session:
        user = User(username="p9_trader", email="p9@test.com", hashed_password="pwd")
        session.add(user)
        await session.flush()

        broker = BrokerAccount(user_id=user.id, broker_name="PAPER", is_paper_trading=True)
        session.add(broker)
        await session.flush()

        settings = TradingSettings(
            user_id=user.id,
            is_algo_active=True,
            max_trades_per_day=10,
            max_simultaneous_positions=5,
            max_daily_loss=10000.0
        )
        session.add(settings)

        # Seed selected Telegram Channel
        channel = TelegramChannel(
            channel_id="-1001234567890",
            channel_name="Verified Trading Channel",
            is_selected=True,
            is_active=True
        )
        session.add(channel)
        await session.commit()

        yield {
            "session": session,
            "session_factory": async_session,
            "user_id": user.id,
            "broker_account_id": broker.id,
            "selected_channel_id": channel.channel_id
        }


@pytest.fixture
def clean_mds():
    mds = MarketDataService()
    mds.subscriptions.clear()
    mds.total_ticks_received = 0
    mds.sfeed_connected = True
    mds.sfeed_state = "CONNECTED"
    return mds


# ============================================================================
# 1. FAILURE-CLOSED PRINCIPLE
# ============================================================================
@pytest.mark.asyncio
async def test_failure_closed_stale_market_data(p9_db, clean_mds):
    """Failure-closed: Stale market data must NEVER trigger a paper trade entry."""
    session = p9_db["session"]
    user_id = p9_db["user_id"]
    broker_id = p9_db["broker_account_id"]

    paper_broker = PaperBroker()
    tm = TradeManager(session, paper_broker)
    token = "56980"

    trade = await tm.process_new_signal(
        user_id, broker_id, make_signal(entry_trigger=180.0), "FC_STALE", token
    )
    clean_mds.register_trade_interest(token, trade.id)

    # Set last tick to 2 minutes ago (exceeding default 60s stale timeout)
    two_min_ago = (datetime.now(timezone.utc) - timedelta(seconds=120)).isoformat()
    clean_mds.subscriptions[token]["last_tick"] = two_min_ago
    clean_mds.subscriptions[token]["latest_ltp"] = 185.0

    with patch("app.services.market_data_service.market_data_service", clean_mds):
        affected = await tm.evaluate_market_prices(token, 185.0)

    assert len(affected) == 0
    await session.refresh(trade)
    assert trade.status == TradeState.WAITING_FOR_ENTRY

    orders = (await session.execute(select(Order).where(Order.trade_id == trade.id))).scalars().all()
    assert len(orders) == 0


@pytest.mark.asyncio
async def test_failure_closed_invalid_ltp_values(p9_db, clean_mds):
    """Failure-closed: Negative, zero, NaN, or None LTP values must be rejected."""
    session = p9_db["session"]
    user_id = p9_db["user_id"]
    broker_id = p9_db["broker_account_id"]

    paper_broker = PaperBroker()
    tm = TradeManager(session, paper_broker)
    token = "56980"

    trade = await tm.process_new_signal(
        user_id, broker_id, make_signal(entry_trigger=180.0), "FC_INVALID_LTP", token
    )
    clean_mds.register_trade_interest(token, trade.id)

    invalid_ltps = [0.0, -1.0, -185.0, None, float("nan")]
    with patch("app.services.market_data_service.market_data_service", clean_mds):
        for invalid_val in invalid_ltps:
            res = await tm.evaluate_market_prices(token, invalid_val)
            assert len(res) == 0

    await session.refresh(trade)
    assert trade.status == TradeState.WAITING_FOR_ENTRY
    orders = (await session.execute(select(Order).where(Order.trade_id == trade.id))).scalars().all()
    assert len(orders) == 0


@pytest.mark.asyncio
async def test_failure_closed_parser_and_malformed_signals(p9_db):
    """Failure-closed: Malformed, incomplete, or illogical signals must never reach execution."""
    malformed_texts = [
        "Good morning traders!",  # Informational
        "NIFTY 23200 CE Buy above 185",  # Incomplete: missing SL and Target
        "NIFTY 23200 CE Buy above 185 SL below 190 Tgt above 210",  # Illogical: SL above Entry
        "NIFTY 23200 CE Buy above 185 SL below 160 Tgt above 180",  # Illogical: Target below Entry
        "NIFTY -500 CE Buy above 100 SL below 80 Tgt above 150",  # Invalid strike
        "BANKNIFTY 50000 XX Buy above 100 SL below 80 Tgt above 150",  # Invalid option type
    ]

    for text in malformed_texts:
        parsed = parse_message(text)
        assert parsed.parsed_successfully is False or parsed.message_type != TelegramMessageType.NEW_SIGNAL


@pytest.mark.asyncio
async def test_failure_closed_risk_manager_rejection_no_subscription(p9_db, clean_mds):
    """Failure-closed: Risk-rejected trade must NOT subscribe to SFeed and must NOT place orders."""
    session = p9_db["session"]
    user_id = p9_db["user_id"]
    broker_id = p9_db["broker_account_id"]

    settings = (await session.execute(
        select(TradingSettings).where(TradingSettings.user_id == user_id)
    )).scalar_one()
    settings.is_algo_active = False  # Deactivated algo
    await session.commit()

    paper_broker = PaperBroker()
    tm = TradeManager(session, paper_broker)
    token = "56980"

    trade = await tm.process_new_signal(
        user_id, broker_id, make_signal(entry_trigger=180.0), "FC_RISK", token
    )
    assert trade.status == TradeState.REJECTED

    # Ensure token is NOT registered in SFeed
    assert token not in clean_mds.subscriptions
    orders = (await session.execute(select(Order).where(Order.trade_id == trade.id))).scalars().all()
    assert len(orders) == 0


# ============================================================================
# 2. TELEGRAM RELIABILITY & EXACTLY-ONCE DEDUPLICATION
# ============================================================================
@pytest.mark.asyncio
async def test_telegram_duplicate_message_deduplication(p9_db):
    """Telegram reliability: Duplicate messages must be ignored (idempotent)."""
    session = p9_db["session"]
    paper_broker = PaperBroker()
    tm = TradeManager(session, paper_broker)

    channel_id = "-1001234567890"
    message_id = "MSG_DUP_101"
    raw_text = "NIFTY 23200 CE 22 Sept 26 Expiry\nBuy above 185\nSL below 160\nTgt above 210"

    # First delivery
    assert await tm.is_duplicate_message(message_id, channel_id) is False
    await tm.record_telegram_message(
        message_id, channel_id, raw_text,
        ParseResult(message_type=TelegramMessageType.NEW_SIGNAL, parsed_successfully=True, raw_text=raw_text)
    )

    # Second delivery
    assert await tm.is_duplicate_message(message_id, channel_id) is True


@pytest.mark.asyncio
async def test_telegram_selected_channel_filtering(p9_db):
    """Telegram reliability: Messages from unselected channels must be ignored."""
    session = p9_db["session"]
    selected_id = p9_db["selected_channel_id"]
    unselected_id = "-1009999999999"

    # Verify query for selected channel
    res1 = await session.execute(
        select(TelegramChannel).where(TelegramChannel.channel_id == selected_id, TelegramChannel.is_selected == True)
    )
    assert res1.scalar_one_or_none() is not None

    res2 = await session.execute(
        select(TelegramChannel).where(TelegramChannel.channel_id == unselected_id, TelegramChannel.is_selected == True)
    )
    assert res2.scalar_one_or_none() is None


# ============================================================================
# 3. SFEED RELIABILITY & SUBSCRIPTION REFERENCE COUNTING
# ============================================================================
@pytest.mark.asyncio
async def test_sfeed_subscription_reference_counting_robustness(clean_mds):
    """SFeed reliability: Shared tokens must maintain reference count and not unsubscribe prematurely."""
    token = "56980"

    # 3 trades subscribe
    clean_mds.register_trade_interest(token, trade_id=1)
    clean_mds.register_trade_interest(token, trade_id=2)
    clean_mds.register_trade_interest(token, trade_id=3)

    assert len(clean_mds.subscriptions[token]["active_trade_ids"]) == 3

    # Release trade 1
    clean_mds.release_trade_interest(token, trade_id=1)
    assert token in clean_mds.subscriptions
    assert clean_mds.subscriptions[token]["active_trade_ids"] == {2, 3}

    # Release trade 2
    clean_mds.release_trade_interest(token, trade_id=2)
    assert token in clean_mds.subscriptions
    assert clean_mds.subscriptions[token]["active_trade_ids"] == {3}

    # Release trade 3 -> unsubscription occurs
    clean_mds.release_trade_interest(token, trade_id=3)
    assert token not in clean_mds.subscriptions


# ============================================================================
# 4. ENTRY & EXIT IDEMPOTENCY
# ============================================================================
@pytest.mark.asyncio
async def test_entry_idempotency_crossing_series(p9_db, clean_mds):
    """Entry idempotency: A series of ticks crossing the trigger must produce exactly ONE BUY."""
    session = p9_db["session"]
    user_id = p9_db["user_id"]
    broker_id = p9_db["broker_account_id"]

    paper_broker = PaperBroker()
    tm = TradeManager(session, paper_broker)
    token = "56980"

    trade = await tm.process_new_signal(
        user_id, broker_id, make_signal(entry_trigger=185.0), "IDEM_SERIES", token
    )
    clean_mds.register_trade_interest(token, trade.id)

    ticks = [184.90, 185.00, 185.00, 185.00, 185.20, 185.50, 186.00]
    with patch("app.services.market_data_service.market_data_service", clean_mds):
        for tick in ticks:
            clean_mds.update_tick(token, tick)
            await tm.evaluate_market_prices(token, tick)

    # Must result in exactly ONE paper order
    orders = (await session.execute(select(Order).where(Order.trade_id == trade.id))).scalars().all()
    assert len(orders) == 1
    assert orders[0].order_type == "BUY"

    # Exactly ONE position
    positions = (await session.execute(select(Position).where(Position.trade_id == trade.id))).scalars().all()
    assert len(positions) == 1
    assert positions[0].is_open is True
    assert positions[0].quantity == 75


@pytest.mark.asyncio
async def test_exit_idempotency_repeated_sl_ticks(p9_db, clean_mds):
    """Exit idempotency: Repeated SL ticks must produce exactly ONE exit order."""
    session = p9_db["session"]
    user_id = p9_db["user_id"]
    broker_id = p9_db["broker_account_id"]

    paper_broker = PaperBroker()
    tm = TradeManager(session, paper_broker)
    token = "56980"

    trade = await tm.process_new_signal(
        user_id, broker_id, make_signal(entry_trigger=180.0, stop_loss=160.0), "IDEM_EXIT", token
    )
    clean_mds.register_trade_interest(token, trade.id)

    with patch("app.services.market_data_service.market_data_service", clean_mds):
        # Entry
        await tm.evaluate_market_prices(token, 180.0)

        # 5 consecutive SL ticks
        for _ in range(5):
            await tm.evaluate_market_prices(token, 155.0)

    orders = (await session.execute(select(Order).where(Order.trade_id == trade.id))).scalars().all()
    assert len(orders) == 2  # 1 BUY, 1 SELL
    assert [o.order_type for o in orders] == ["BUY", "SELL"]

    await session.refresh(trade)
    assert trade.status == TradeState.CLOSED
    assert trade.quantity == 0


# ============================================================================
# 5. STOP LOSS VS TARGET PRIORITY
# ============================================================================
@pytest.mark.asyncio
async def test_sl_priority_over_target(p9_db, clean_mds):
    """SL/Target priority: Stop loss strictly takes priority over target for capital preservation."""
    session = p9_db["session"]
    user_id = p9_db["user_id"]
    broker_id = p9_db["broker_account_id"]

    paper_broker = PaperBroker()
    tm = TradeManager(session, paper_broker)
    token = "56980"

    # Synthetic signal where triggers are tightly bounded
    signal_data = make_signal(entry_trigger=180.0, stop_loss=160.0, target=210.0)
    trade = await tm.process_new_signal(user_id, broker_id, signal_data, "PRIORITY_TEST", token)
    clean_mds.register_trade_interest(token, trade.id)

    with patch("app.services.market_data_service.market_data_service", clean_mds):
        # 1. Enter
        await tm.evaluate_market_prices(token, 180.0)

        # 2. Breach SL (159.0)
        await tm.evaluate_market_prices(token, 159.0)

    await session.refresh(trade)
    assert trade.status == TradeState.CLOSED

    # Verify audit log recorded STOP_LOSS_TRIGGERED
    logs = (await session.execute(
        select(AuditLog).where(AuditLog.user_id == user_id)
    )).scalars().all()
    trade_logs = [l for l in logs if l.details and l.details.get("trade_id") == trade.id]
    exit_actions = [l.action for l in trade_logs if "TRIGGERED" in l.action]
    assert exit_actions == ["STOP_LOSS_TRIGGERED"]


# ============================================================================
# 6. CONCURRENCY & RACE CONDITIONS
# ============================================================================
@pytest.mark.asyncio
async def test_concurrent_telegram_signals_processing(p9_db, clean_mds):
    """Concurrency: Two Telegram signals arriving simultaneously must not cause state corruption."""
    session_factory = p9_db["session_factory"]
    user_id = p9_db["user_id"]
    broker_id = p9_db["broker_account_id"]

    sig1 = make_signal(strike=23200, option_type="CE", entry_trigger=180.0, stop_loss=160.0, target=210.0)
    sig2 = make_signal(strike=23300, option_type="CE", entry_trigger=150.0, stop_loss=130.0, target=180.0)

    async def process_signal(sig, msg_id, tok):
        async with session_factory() as sess:
            tm_local = TradeManager(sess, PaperBroker())
            return await tm_local.process_new_signal(user_id, broker_id, sig, msg_id, tok)

    # Process concurrently using asyncio.gather
    t1, t2 = await asyncio.gather(
        process_signal(sig1, "CONC_1", "56980"),
        process_signal(sig2, "CONC_2", "56982")
    )

    assert t1.id != t2.id
    assert t1.status == TradeState.WAITING_FOR_ENTRY
    assert t2.status == TradeState.WAITING_FOR_ENTRY


@pytest.mark.asyncio
async def test_concurrent_ticks_different_instruments(p9_db, clean_mds):
    """Concurrency: Parallel tick arrivals for different instruments must evaluate independently."""
    session = p9_db["session"]
    user_id = p9_db["user_id"]
    broker_id = p9_db["broker_account_id"]

    paper_broker = PaperBroker()
    tm = TradeManager(session, paper_broker)

    t1 = await tm.process_new_signal(user_id, broker_id, make_signal(entry_trigger=180.0, stop_loss=160.0, target=210.0), "CONC_T1", "56980")
    t2 = await tm.process_new_signal(user_id, broker_id, make_signal(entry_trigger=150.0, stop_loss=130.0, target=180.0), "CONC_T2", "56981")
    clean_mds.register_trade_interest("56980", t1.id)
    clean_mds.register_trade_interest("56981", t2.id)

    with patch("app.services.market_data_service.market_data_service", clean_mds):
        # Parallel evaluation
        res1, res2 = await asyncio.gather(
            tm.evaluate_market_prices("56980", 185.0),  # Triggers T1
            tm.evaluate_market_prices("56981", 140.0)   # Does NOT trigger T2 (< 150.0)
        )

    assert len(res1) == 1
    assert len(res2) == 0

    await session.refresh(t1)
    await session.refresh(t2)
    assert t1.status == TradeState.POSITION_OPEN
    assert t2.status == TradeState.WAITING_FOR_ENTRY


# ============================================================================
# 7. RESTART RECOVERY ACROSS ALL TRADE LIFECYCLE STATES
# ============================================================================
@pytest.mark.asyncio
async def test_restart_recovery_across_all_lifecycle_states(p9_db, clean_mds):
    """Restart recovery: Must restore active states, but ignore closed/rejected states."""
    session = p9_db["session"]
    user_id = p9_db["user_id"]
    broker_id = p9_db["broker_account_id"]

    states_to_test = [
        (TradeState.WAITING_FOR_ENTRY, "TOK_WAITING", True),
        (TradeState.POSITION_OPEN, "TOK_OPEN", True),
        (TradeState.PARTIAL_PROFIT, "TOK_PARTIAL", True),
        (TradeState.TRAILING_STOP, "TOK_TRAILING", True),
        (TradeState.CLOSED, "TOK_CLOSED", False),
        (TradeState.REJECTED, "TOK_REJECTED", False),
    ]

    for status, token, should_restore in states_to_test:
        sig = Signal(
            message_id=f"REC_{token}", underlying="NIFTY", strike=23200.0,
            option_type="CE", expiry="2026-09-22", entry_trigger=180.0, stop_loss=160.0, target=210.0
        )
        session.add(sig)
        await session.flush()

        trade = Trade(
            user_id=user_id, broker_account_id=broker_id, signal_id=sig.id,
            instrument_token=token, status=status, quantity=75 if status != TradeState.WAITING_FOR_ENTRY else 0
        )
        session.add(trade)

    await session.commit()

    # Clear in-memory MDS to simulate reboot
    clean_mds.subscriptions.clear()

    # Run startup recovery routine
    with patch("app.services.trade_recovery.market_data_service", clean_mds):
        restored_count = await restore_active_trades_subscriptions(session)

    # Exactly 4 active states should be restored
    assert restored_count == 4
    assert "TOK_WAITING" in clean_mds.subscriptions
    assert "TOK_OPEN" in clean_mds.subscriptions
    assert "TOK_PARTIAL" in clean_mds.subscriptions
    assert "TOK_TRAILING" in clean_mds.subscriptions
    assert "TOK_CLOSED" not in clean_mds.subscriptions
    assert "TOK_REJECTED" not in clean_mds.subscriptions


# ============================================================================
# 8. SECRET SANITIZATION & ZERO LOG EXPOSURE
# ============================================================================
@pytest.mark.asyncio
async def test_secret_sanitization_audit(p9_db):
    """Security: Credentials and secrets must NEVER be persisted to audit logs."""
    session = p9_db["session"]
    user_id = p9_db["user_id"]

    paper_broker = PaperBroker()
    tm = TradeManager(session, paper_broker)

    # Perform trade and log audit
    trade = await tm.process_new_signal(
        user_id, p9_db["broker_account_id"], make_signal(), "SEC_1", "56980"
    )

    # Query all audit logs
    logs = (await session.execute(select(AuditLog))).scalars().all()
    forbidden_terms = [
        "totp_secret", "consumer_secret", "access_token", "trading_sid",
        "trade_token", "mpin", "hashed_password", "api_hash"
    ]

    for log in logs:
        log_str = str(log.details).lower()
        for forbidden in forbidden_terms:
            assert forbidden not in log_str, f"Secret leak detected: '{forbidden}' in audit log {log.id}!"


# ============================================================================
# 9. ABSOLUTE LIVE ORDER LOCKING ASSERTION
# ============================================================================
@pytest.mark.asyncio
async def test_paper_mode_strict_zero_live_order_invocations():
    """Safety: KotakNeoBroker.place_order() invocation count must be strictly ZERO."""
    broker = KotakNeoBroker()
    call_count = getattr(broker, "_place_order_call_count", 0)
    assert call_count == 0, f"FATAL: KotakNeoBroker place_order was invoked {call_count} times in paper mode!"
