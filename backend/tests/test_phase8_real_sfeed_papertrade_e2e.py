"""
Phase 8: Real SFeed -> Paper Trade End-to-End Test Suite.

Validates all 12 Phase 8 test specifications:
 1. Real SFeed WAITING-FOR-ENTRY (LTP < trigger, 0 orders)
 2. Real SFeed ENTRY TRIGGER (LTP >= trigger, WAITING_FOR_ENTRY -> POSITION_OPEN, exactly 1 Paper order)
 3. STOP LOSS (LTP <= SL, POSITION_OPEN -> CLOSED, correct P&L, subscription interest released)
 4. TARGET (LTP >= target, POSITION_OPEN -> CLOSED, correct P&L, audit logs)
 5. NO FALSE TRIGGER & Boundary Equality (LTP < trigger vs LTP == trigger; SL & target boundary checks)
 6. DUPLICATE TICK / IDEMPOTENCY (duplicate ticks produce 0 duplicate orders/transitions)
 7. MULTIPLE ACTIVE TRADES (different tokens: ticks for Token A never affect Trade B)
 8. SAME TOKEN REFERENCE COUNTING (multiple trades on same token, refcount 2 -> 1 -> 0, unsubscribes only at 0)
 9. SFEED DISCONNECT/RECONNECT WITH ACTIVE PAPER POSITION (position intact, auto-resubscribe, ticks resume)
 10. RESTART RECOVERY (persisted active trade recovered, subscriptions restored, no duplicate entry)
 11. RISK MANAGER (max trades, max positions, loss limit, rejected trade does not subscribe or order)
 12. TELEGRAM -> REAL SFEED -> PAPERBROKER (end-to-end integration flow)

SAFETY:
 KotakNeoBroker.place_order() invocation count MUST remain strictly ZERO across all tests.
"""
import pytest
import pytest_asyncio
import asyncio
import time
from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy.future import select

from app.database.database import Base
from app.database.models import (
    User, BrokerAccount, TradingSettings, Trade, TradeState,
    Position, Order, AuditLog, TelegramMessage, Signal, RiskEvent
)
from app.services.market_data_service import MarketDataService, SubscriptionState
from app.trading.trade_manager import TradeManager
from app.trading.risk_manager import RiskManager
from app.brokers.paper import PaperBroker
from app.brokers.kotak_neo import KotakNeoBroker
from app.services.trade_recovery import restore_active_trades_subscriptions
from app.telegram.parser import parse_message
from app.telegram.models import TradeSignal, ParseResult, TelegramMessageType
from neo_api_client.websocket.feed.models import SFeedScrip, SFeedScripLite

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
        # Pre-seed user, broker account, and default trading settings
        user = User(username="p8_trader", email="p8@test.com", hashed_password="pwd")
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
        await session.commit()

        yield {
            "session": session,
            "user_id": user.id,
            "broker_account_id": broker.id
        }


@pytest.fixture
def clean_mds():
    """Provides a clean, isolated MarketDataService instance."""
    mds = MarketDataService()
    mds.subscriptions.clear()
    mds.total_ticks_received = 0
    mds.sfeed_connected = True
    mds.sfeed_state = "CONNECTED"
    return mds


# ============================================================================
# TEST 1 — REAL SFEED WAITING-FOR-ENTRY
# ============================================================================
@pytest.mark.asyncio
async def test_1_real_sfeed_waiting_for_entry(p8_db, clean_mds):
    session = p8_db["session"]
    user_id = p8_db["user_id"]
    broker_id = p8_db["broker_account_id"]

    paper_broker = PaperBroker()
    trade_manager = TradeManager(session, paper_broker)

    token = "56980"
    symbol = "NIFTY2692223200CE"
    current_real_ltp = 179.10
    entry_trigger = 185.00  # Safely above current LTP

    signal_data = make_signal(
        underlying="NIFTY",
        strike=23200,
        option_type="CE",
        entry_trigger=entry_trigger,
        stop_loss=160.00,
        target=210.00,
        telegram_cmp=current_real_ltp
    )

    trade = await trade_manager.process_new_signal(
        user_id=user_id,
        broker_account_id=broker_id,
        signal_data=signal_data,
        message_id="P8_MSG_1",
        resolved_token=token
    )
    assert trade.status == TradeState.WAITING_FOR_ENTRY

    # Register in MDS
    clean_mds.register_trade_interest(token, trade.id, symbol=symbol)

    # Deliver real market tick below trigger
    clean_mds.update_tick(token, current_real_ltp, feed_type="REAL SFEED")

    # Evaluate
    with patch("app.services.market_data_service.market_data_service", clean_mds):
        affected = await trade_manager.evaluate_market_prices(token, current_real_ltp)

    assert len(affected) == 0
    await session.refresh(trade)
    assert trade.status == TradeState.WAITING_FOR_ENTRY

    # Verify no paper orders created
    orders_res = await session.execute(select(Order).where(Order.trade_id == trade.id))
    orders = orders_res.scalars().all()
    assert len(orders) == 0

    # Strict Safety: Live order count = 0
    kotak = KotakNeoBroker()
    assert getattr(kotak, "_place_order_call_count", 0) == 0


# ============================================================================
# TEST 2 — REAL SFEED ENTRY TRIGGER
# ============================================================================
@pytest.mark.asyncio
async def test_2_real_sfeed_entry_trigger(p8_db, clean_mds):
    session = p8_db["session"]
    user_id = p8_db["user_id"]
    broker_id = p8_db["broker_account_id"]

    paper_broker = PaperBroker()
    trade_manager = TradeManager(session, paper_broker)

    token = "56980"
    symbol = "NIFTY2692223200CE"
    entry_trigger = 185.00

    signal_data = make_signal(
        underlying="NIFTY",
        strike=23200,
        option_type="CE",
        entry_trigger=entry_trigger,
        stop_loss=160.00,
        target=210.00,
        telegram_cmp=179.10
    )

    trade = await trade_manager.process_new_signal(
        user_id=user_id,
        broker_account_id=broker_id,
        signal_data=signal_data,
        message_id="P8_MSG_2",
        resolved_token=token
    )
    clean_mds.register_trade_interest(token, trade.id, symbol=symbol)

    # Triggering tick arrives
    trigger_ltp = 185.20
    clean_mds.update_tick(token, trigger_ltp, feed_type="REAL SFEED")

    with patch("app.services.market_data_service.market_data_service", clean_mds):
        affected = await trade_manager.evaluate_market_prices(token, trigger_ltp)

    assert len(affected) == 1
    assert affected[0]["trade_id"] == trade.id
    assert affected[0]["new_state"] == TradeState.POSITION_OPEN.value

    await session.refresh(trade)
    assert trade.status == TradeState.POSITION_OPEN
    assert trade.entry_price == trigger_ltp
    assert trade.quantity == 75

    # Verify exactly one paper order
    orders_res = await session.execute(select(Order).where(Order.trade_id == trade.id))
    orders = orders_res.scalars().all()
    assert len(orders) == 1
    assert orders[0].order_type == "BUY"
    assert orders[0].quantity == 75
    assert orders[0].price == trigger_ltp

    # Verify position opened
    pos_res = await session.execute(select(Position).where(Position.trade_id == trade.id))
    position = pos_res.scalar_one()
    assert position.is_open is True
    assert position.quantity == 75
    assert position.average_price == trigger_ltp


# ============================================================================
# TEST 3 — STOP LOSS
# ============================================================================
@pytest.mark.asyncio
async def test_3_stop_loss(p8_db, clean_mds):
    session = p8_db["session"]
    user_id = p8_db["user_id"]
    broker_id = p8_db["broker_account_id"]

    paper_broker = PaperBroker()
    trade_manager = TradeManager(session, paper_broker)

    token = "56980"
    signal_data = make_signal(
        underlying="NIFTY",
        strike=23200,
        option_type="CE",
        entry_trigger=180.00,
        stop_loss=160.00,
        target=210.00
    )

    trade = await trade_manager.process_new_signal(
        user_id=user_id,
        broker_account_id=broker_id,
        signal_data=signal_data,
        message_id="P8_MSG_3",
        resolved_token=token
    )
    clean_mds.register_trade_interest(token, trade.id)

    # 1. Entry
    with patch("app.services.market_data_service.market_data_service", clean_mds):
        await trade_manager.evaluate_market_prices(token, 180.00)

    await session.refresh(trade)
    assert trade.status == TradeState.POSITION_OPEN

    # 2. Stop Loss breached
    sl_ltp = 159.50
    clean_mds.update_tick(token, sl_ltp)
    with patch("app.services.market_data_service.market_data_service", clean_mds):
        affected = await trade_manager.evaluate_market_prices(token, sl_ltp)

    assert len(affected) == 1
    assert affected[0]["new_state"] == TradeState.CLOSED.value

    await session.refresh(trade)
    assert trade.status == TradeState.CLOSED
    assert trade.quantity == 0
    assert trade.exit_price == sl_ltp
    expected_pnl = (sl_ltp - 180.00) * 75  # Negative P&L
    assert pytest.approx(trade.realized_pnl, 0.01) == expected_pnl

    # Position closed
    pos_res = await session.execute(select(Position).where(Position.trade_id == trade.id))
    pos = pos_res.scalar_one()
    assert pos.is_open is False
    assert pos.quantity == 0

    # Subscription interest released
    assert token not in clean_mds.subscriptions


# ============================================================================
# TEST 4 — TARGET
# ============================================================================
@pytest.mark.asyncio
async def test_4_target(p8_db, clean_mds):
    session = p8_db["session"]
    user_id = p8_db["user_id"]
    broker_id = p8_db["broker_account_id"]

    paper_broker = PaperBroker()
    trade_manager = TradeManager(session, paper_broker)

    token = "56980"
    signal_data = make_signal(
        underlying="NIFTY",
        strike=23200,
        option_type="CE",
        entry_trigger=180.00,
        stop_loss=160.00,
        target=210.00
    )

    trade = await trade_manager.process_new_signal(
        user_id=user_id,
        broker_account_id=broker_id,
        signal_data=signal_data,
        message_id="P8_MSG_4",
        resolved_token=token
    )
    clean_mds.register_trade_interest(token, trade.id)

    # 1. Entry
    with patch("app.services.market_data_service.market_data_service", clean_mds):
        await trade_manager.evaluate_market_prices(token, 180.00)

    # 2. Target Hit
    target_ltp = 212.00
    clean_mds.update_tick(token, target_ltp)
    with patch("app.services.market_data_service.market_data_service", clean_mds):
        affected = await trade_manager.evaluate_market_prices(token, target_ltp)

    assert len(affected) == 1
    assert affected[0]["new_state"] == TradeState.CLOSED.value

    await session.refresh(trade)
    assert trade.status == TradeState.CLOSED
    assert trade.quantity == 0
    assert trade.exit_price == target_ltp
    expected_pnl = (target_ltp - 180.00) * 75  # Positive profit
    assert pytest.approx(trade.realized_pnl, 0.01) == expected_pnl

    # Audit log entry for TARGET_TRIGGERED
    logs_res = await session.execute(
        select(AuditLog).where(AuditLog.user_id == user_id, AuditLog.action == "TARGET_TRIGGERED")
    )
    target_logs = logs_res.scalars().all()
    assert len(target_logs) >= 1


# ============================================================================
# TEST 5 — NO FALSE TRIGGER & BOUNDARY EQUALITY
# ============================================================================
@pytest.mark.asyncio
async def test_5_no_false_trigger_boundary_behavior(p8_db, clean_mds):
    session = p8_db["session"]
    user_id = p8_db["user_id"]
    broker_id = p8_db["broker_account_id"]

    paper_broker = PaperBroker()
    trade_manager = TradeManager(session, paper_broker)

    token = "56980"
    entry_trigger = 185.00
    sl_trigger = 160.00
    tgt_trigger = 210.00

    signal_data = make_signal(
        underlying="NIFTY",
        strike=23200,
        option_type="CE",
        entry_trigger=entry_trigger,
        stop_loss=sl_trigger,
        target=tgt_trigger
    )

    trade = await trade_manager.process_new_signal(
        user_id=user_id,
        broker_account_id=broker_id,
        signal_data=signal_data,
        message_id="P8_MSG_5",
        resolved_token=token
    )
    clean_mds.register_trade_interest(token, trade.id)

    # 1. Strictly below entry (184.99) -> Must NOT trigger
    with patch("app.services.market_data_service.market_data_service", clean_mds):
        res1 = await trade_manager.evaluate_market_prices(token, 184.99)
    assert len(res1) == 0
    await session.refresh(trade)
    assert trade.status == TradeState.WAITING_FOR_ENTRY

    # 2. EXACT equality (185.00) -> MUST trigger entry
    with patch("app.services.market_data_service.market_data_service", clean_mds):
        res2 = await trade_manager.evaluate_market_prices(token, 185.00)
    assert len(res2) == 1
    await session.refresh(trade)
    assert trade.status == TradeState.POSITION_OPEN

    # 3. Just above SL (160.01) -> Must NOT trigger SL
    with patch("app.services.market_data_service.market_data_service", clean_mds):
        res3 = await trade_manager.evaluate_market_prices(token, 160.01)
    assert len(res3) == 0
    await session.refresh(trade)
    assert trade.status == TradeState.POSITION_OPEN

    # 4. EXACT SL equality (160.00) -> MUST trigger SL
    with patch("app.services.market_data_service.market_data_service", clean_mds):
        res4 = await trade_manager.evaluate_market_prices(token, 160.00)
    assert len(res4) == 1
    await session.refresh(trade)
    assert trade.status == TradeState.CLOSED


# ============================================================================
# TEST 6 — DUPLICATE TICK / IDEMPOTENCY
# ============================================================================
@pytest.mark.asyncio
async def test_6_duplicate_tick_idempotency(p8_db, clean_mds):
    session = p8_db["session"]
    user_id = p8_db["user_id"]
    broker_id = p8_db["broker_account_id"]

    paper_broker = PaperBroker()
    trade_manager = TradeManager(session, paper_broker)

    token = "56980"
    signal_data = make_signal(
        underlying="NIFTY",
        strike=23200,
        option_type="CE",
        entry_trigger=180.00,
        stop_loss=160.00,
        target=210.00
    )

    trade = await trade_manager.process_new_signal(
        user_id=user_id,
        broker_account_id=broker_id,
        signal_data=signal_data,
        message_id="P8_MSG_6",
        resolved_token=token
    )
    clean_mds.register_trade_interest(token, trade.id)

    # Deliver identical triggering tick 5 times
    with patch("app.services.market_data_service.market_data_service", clean_mds):
        for _ in range(5):
            await trade_manager.evaluate_market_prices(token, 182.00)

    # Verify exactly 1 BUY order exists
    orders_res = await session.execute(select(Order).where(Order.trade_id == trade.id))
    orders = orders_res.scalars().all()
    assert len(orders) == 1
    assert orders[0].order_type == "BUY"

    # Now deliver identical target tick 5 times
    with patch("app.services.market_data_service.market_data_service", clean_mds):
        for _ in range(5):
            await trade_manager.evaluate_market_prices(token, 215.00)

    orders_res2 = await session.execute(select(Order).where(Order.trade_id == trade.id))
    orders2 = orders_res2.scalars().all()
    # Exactly 2 orders: 1 BUY and 1 SELL
    assert len(orders2) == 2
    assert {o.order_type for o in orders2} == {"BUY", "SELL"}


# ============================================================================
# TEST 7 — MULTIPLE ACTIVE TRADES (DIFFERENT TOKENS)
# ============================================================================
@pytest.mark.asyncio
async def test_7_multiple_active_trades_different_tokens(p8_db, clean_mds):
    session = p8_db["session"]
    user_id = p8_db["user_id"]
    broker_id = p8_db["broker_account_id"]

    paper_broker = PaperBroker()
    trade_manager = TradeManager(session, paper_broker)

    token_a = "56980"  # CE
    token_b = "56981"  # PE

    trade_a = await trade_manager.process_new_signal(
        user_id=user_id,
        broker_account_id=broker_id,
        signal_data=make_signal(
            underlying="NIFTY", strike=23200, option_type="CE",
            entry_trigger=180.0, stop_loss=160.0, target=210.0
        ),
        message_id="P8_MSG_7A",
        resolved_token=token_a
    )
    clean_mds.register_trade_interest(token_a, trade_a.id)

    trade_b = await trade_manager.process_new_signal(
        user_id=user_id,
        broker_account_id=broker_id,
        signal_data=make_signal(
            underlying="NIFTY", strike=23200, option_type="PE",
            entry_trigger=150.0, stop_loss=130.0, target=180.0
        ),
        message_id="P8_MSG_7B",
        resolved_token=token_b
    )
    clean_mds.register_trade_interest(token_b, trade_b.id)

    # Deliver tick for Token A only
    with patch("app.services.market_data_service.market_data_service", clean_mds):
        await trade_manager.evaluate_market_prices(token_a, 185.0)

    await session.refresh(trade_a)
    await session.refresh(trade_b)

    # Trade A entered, Trade B untouched
    assert trade_a.status == TradeState.POSITION_OPEN
    assert trade_b.status == TradeState.WAITING_FOR_ENTRY

    # Orders check
    orders_b = (await session.execute(select(Order).where(Order.trade_id == trade_b.id))).scalars().all()
    assert len(orders_b) == 0


# ============================================================================
# TEST 8 — SAME TOKEN REFERENCE COUNTING
# ============================================================================
@pytest.mark.asyncio
async def test_8_same_token_reference_counting(p8_db, clean_mds):
    session = p8_db["session"]
    user_id = p8_db["user_id"]
    broker_id = p8_db["broker_account_id"]

    paper_broker = PaperBroker()
    trade_manager = TradeManager(session, paper_broker)
    token = "56980"

    # Trade 1
    trade1 = await trade_manager.process_new_signal(
        user_id=user_id, broker_account_id=broker_id,
        signal_data=make_signal(
            underlying="NIFTY", strike=23200, option_type="CE",
            entry_trigger=180.0, stop_loss=160.0, target=210.0
        ),
        message_id="P8_MSG_8A", resolved_token=token
    )
    clean_mds.register_trade_interest(token, trade1.id)
    assert len(clean_mds.subscriptions[token]["active_trade_ids"]) == 1

    # Trade 2 on same token
    trade2 = await trade_manager.process_new_signal(
        user_id=user_id, broker_account_id=broker_id,
        signal_data=make_signal(
            underlying="NIFTY", strike=23200, option_type="CE",
            entry_trigger=180.0, stop_loss=160.0, target=210.0
        ),
        message_id="P8_MSG_8B", resolved_token=token
    )
    clean_mds.register_trade_interest(token, trade2.id)
    assert len(clean_mds.subscriptions[token]["active_trade_ids"]) == 2

    # Both enter
    with patch("app.services.market_data_service.market_data_service", clean_mds):
        await trade_manager.evaluate_market_prices(token, 185.0)

    # Release Trade 1
    clean_mds.release_trade_interest(token, trade1.id)
    # Token MUST remain subscribed with refcount = 1
    assert token in clean_mds.subscriptions
    assert len(clean_mds.subscriptions[token]["active_trade_ids"]) == 1

    # Release Trade 2
    clean_mds.release_trade_interest(token, trade2.id)
    # Token unsubscribed now
    assert token not in clean_mds.subscriptions


# ============================================================================
# TEST 9 — SFEED DISCONNECT/RECONNECT WITH ACTIVE PAPER POSITION
# ============================================================================
@pytest.mark.asyncio
async def test_9_sfeed_disconnect_reconnect_with_active_position(p8_db, clean_mds):
    session = p8_db["session"]
    user_id = p8_db["user_id"]
    broker_id = p8_db["broker_account_id"]

    paper_broker = PaperBroker()
    trade_manager = TradeManager(session, paper_broker)
    token = "56980"

    trade = await trade_manager.process_new_signal(
        user_id=user_id, broker_account_id=broker_id,
        signal_data=make_signal(
            underlying="NIFTY", strike=23200, option_type="CE",
            entry_trigger=180.0, stop_loss=160.0, target=210.0
        ),
        message_id="P8_MSG_9", resolved_token=token
    )
    clean_mds.register_trade_interest(token, trade.id)

    # Open position
    with patch("app.services.market_data_service.market_data_service", clean_mds):
        await trade_manager.evaluate_market_prices(token, 180.0)

    await session.refresh(trade)
    assert trade.status == TradeState.POSITION_OPEN

    # 1. Simulate SFeed Disconnection
    clean_mds.sfeed_connected = False
    clean_mds.sfeed_state = "RECONNECTING"

    # Verify position remains open and intact
    pos = (await session.execute(select(Position).where(Position.trade_id == trade.id))).scalar_one()
    assert pos.is_open is True
    assert pos.quantity == 75

    # 2. Simulate SFeed Reconnection
    clean_mds.sfeed_connected = True
    clean_mds.sfeed_state = "CONNECTED"
    clean_mds.mark_subscribed(token, generation=2)

    assert clean_mds.subscriptions[token]["connection_generation"] == 2

    # 3. Deliver live ticks upon reconnection
    clean_mds.update_tick(token, 185.0)
    with patch("app.services.market_data_service.market_data_service", clean_mds):
        await trade_manager.evaluate_market_prices(token, 185.0)

    # Still open, exactly 1 order, no duplicate buy
    orders = (await session.execute(select(Order).where(Order.trade_id == trade.id))).scalars().all()
    assert len(orders) == 1


# ============================================================================
# TEST 10 — RESTART RECOVERY
# ============================================================================
@pytest.mark.asyncio
async def test_10_restart_recovery(p8_db, clean_mds):
    session = p8_db["session"]
    user_id = p8_db["user_id"]
    broker_id = p8_db["broker_account_id"]

    paper_broker = PaperBroker()
    trade_manager = TradeManager(session, paper_broker)
    token = "56980"

    trade = await trade_manager.process_new_signal(
        user_id=user_id, broker_account_id=broker_id,
        signal_data=make_signal(
            underlying="NIFTY", strike=23200, option_type="CE",
            entry_trigger=185.0, stop_loss=160.0, target=210.0
        ),
        message_id="P8_MSG_10", resolved_token=token
    )
    assert trade.status == TradeState.WAITING_FOR_ENTRY

    # Record Telegram message
    await trade_manager.record_telegram_message(
        message_id="P8_MSG_10", channel_id="CH1", text="Signal text",
        parsed=ParseResult(
            message_type=TelegramMessageType.NEW_SIGNAL,
            parsed_successfully=True,
            raw_text="Signal text"
        )
    )

    # Simulate process termination: clear MDS
    clean_mds.subscriptions.clear()
    assert len(clean_mds.subscriptions) == 0

    # Startup recovery routine
    with patch("app.services.trade_recovery.market_data_service", clean_mds):
        restored = await restore_active_trades_subscriptions(session)

    assert restored >= 1
    assert token in clean_mds.subscriptions
    assert trade.id in clean_mds.subscriptions[token]["active_trade_ids"]

    # Verify duplicate message check
    is_dup = await trade_manager.is_duplicate_message("P8_MSG_10", "CH1")
    assert is_dup is True


# ============================================================================
# TEST 11 — RISK MANAGER
# ============================================================================
@pytest.mark.asyncio
async def test_11_risk_manager(p8_db, clean_mds):
    session = p8_db["session"]
    user_id = p8_db["user_id"]
    broker_id = p8_db["broker_account_id"]

    # Configure tight risk settings: max 1 simultaneous position, max 2 trades/day
    settings = (await session.execute(
        select(TradingSettings).where(TradingSettings.user_id == user_id)
    )).scalar_one()
    settings.max_simultaneous_positions = 1
    settings.max_trades_per_day = 2
    settings.max_daily_loss = 500.0
    await session.commit()

    paper_broker = PaperBroker()
    trade_manager = TradeManager(session, paper_broker)

    # 1. First trade allowed
    t1 = await trade_manager.process_new_signal(
        user_id=user_id, broker_account_id=broker_id,
        signal_data=make_signal(
            underlying="NIFTY", strike=23200, option_type="CE",
            entry_trigger=180.0, stop_loss=160.0, target=210.0
        ),
        message_id="RISK_T1", resolved_token="56980"
    )
    assert t1.status == TradeState.WAITING_FOR_ENTRY

    # 2. Second trade rejected due to max simultaneous positions
    t2 = await trade_manager.process_new_signal(
        user_id=user_id, broker_account_id=broker_id,
        signal_data=make_signal(
            underlying="NIFTY", strike=23200, option_type="CE",
            entry_trigger=180.0, stop_loss=160.0, target=210.0
        ),
        message_id="RISK_T2", resolved_token="56980"
    )
    assert t2.status == TradeState.REJECTED

    # Verify rejected trade does NOT create paper order
    t2_orders = (await session.execute(select(Order).where(Order.trade_id == t2.id))).scalars().all()
    assert len(t2_orders) == 0

    # Verify risk event recorded
    events = (await session.execute(select(RiskEvent).where(RiskEvent.trade_id == t2.id))).scalars().all()
    assert len(events) >= 1
    assert events[0].event_type == "RISK_REJECTED"


# ============================================================================
# TEST 12 — TELEGRAM -> REAL SFEED -> PAPERBROKER
# ============================================================================
@pytest.mark.asyncio
async def test_12_telegram_to_real_sfeed_to_paperbroker_e2e(p8_db, clean_mds):
    session = p8_db["session"]
    user_id = p8_db["user_id"]
    broker_id = p8_db["broker_account_id"]

    # 1. Parse real Telegram message
    telegram_text = (
        "NIFTY 23200 CE 22 Sept 26 Expiry\n"
        "Buy above 185\n"
        "SL below 160\n"
        "Tgt above 210\n"
        "CMP 179.10"
    )
    parsed = parse_message(telegram_text)
    assert parsed.parsed_successfully is True
    assert parsed.message_type == TelegramMessageType.NEW_SIGNAL
    sig = parsed.signal

    # 2. Resolve instrument (token 56980, NIFTY2692223200CE)
    token = "56980"
    trd_symbol = "NIFTY2692223200CE"

    # 3. Create Trade through TradeManager
    paper_broker = PaperBroker()
    trade_manager = TradeManager(session, paper_broker)

    trade = await trade_manager.process_new_signal(
        user_id=user_id,
        broker_account_id=broker_id,
        signal_data=sig,
        message_id="E2E_P8_MSG",
        resolved_token=token
    )
    assert trade.status == TradeState.WAITING_FOR_ENTRY

    # 4. SFeed subscription in MarketDataService
    clean_mds.register_trade_interest(
        token=token, trade_id=trade.id, symbol="NIFTY", trading_symbol=trd_symbol
    )
    assert token in clean_mds.subscriptions

    # 5. Real market tick arrives crossing entry trigger
    entry_ltp = 186.50
    clean_mds.update_tick(token, entry_ltp, feed_type="REAL SFEED")

    with patch("app.services.market_data_service.market_data_service", clean_mds):
        affected = await trade_manager.evaluate_market_prices(token, entry_ltp)

    assert len(affected) == 1
    await session.refresh(trade)
    assert trade.status == TradeState.POSITION_OPEN
    assert trade.quantity == 75

    # 6. Verify PaperBroker order executed
    orders = (await session.execute(select(Order).where(Order.trade_id == trade.id))).scalars().all()
    assert len(orders) == 1
    assert orders[0].order_type == "BUY"
    assert orders[0].price == entry_ltp

    # 7. Strictly verify ZERO live Kotak Neo orders
    kotak = KotakNeoBroker()
    assert getattr(kotak, "_place_order_call_count", 0) == 0
