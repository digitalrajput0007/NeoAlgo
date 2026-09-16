import pytest
import pytest_asyncio
import os
from decimal import Decimal
from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, patch

from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy import event as sa_event

from app.trading.trade_manager import TradeManager
from app.database.models import Trade, Signal, TradingSettings, BrokerAccount, TradeState
from app.database.models import Base
from app.services.market_data_service import market_data_service
from app.telegram.models import TradeSignal as PydanticTradeSignal

pytestmark = pytest.mark.asyncio

TEST_DB_FILE = "test_phase10d.db"
TEST_DB_URL = f"sqlite+aiosqlite:///./{TEST_DB_FILE}"

test_engine = create_async_engine(TEST_DB_URL, echo=False)
TestSessionLocal = async_sessionmaker(test_engine, class_=AsyncSession, expire_on_commit=False)

@pytest_asyncio.fixture(autouse=True)
async def setup_test_db():
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)

@pytest_asyncio.fixture
async def db_session():
    async with TestSessionLocal() as session:
        yield session

@pytest_asyncio.fixture
async def setup_10d_env(db_session):
    # Setup broker account
    broker = BrokerAccount(
        id=1,
        user_id=1,
        broker_name="KOTAK",
        is_paper_trading=True
    )
    db_session.add(broker)

    # Setup settings
    settings = TradingSettings(
        user_id=1,
        is_algo_active=True,
        entry_timeout_minutes=15,
        entry_tolerance=1.5, # Configured tolerance
        max_risk_per_trade=5000.0
    )
    db_session.add(settings)
    
    await db_session.flush()
    from app.brokers.paper import PaperBroker
    paper_broker = PaperBroker()
    
    # Mock resolve_option_contract to avoid needing instrument master data
    async def mock_resolve_option_contract(*args, **kwargs):
        return {"instrument_token": "12345", "lot_size": 15}
    paper_broker.resolve_option_contract = mock_resolve_option_contract

    manager = TradeManager(db_session, paper_broker)
    return manager, broker, settings

async def test_signal_process_saves_bounds(db_session, setup_10d_env):
    manager, broker, settings = setup_10d_env
    
    signal_data = PydanticTradeSignal(
        underlying="BANKNIFTY",
        strike="45000",
        option_type="CE",
        expiry=datetime.now().date(),
        entry_trigger=Decimal("150.0"),
        entry_direction="ABOVE",
        stop_loss=Decimal("120.0"),
        target=Decimal("200.0"),
        telegram_cmp=Decimal("140.0"),
        raw_text="buy above 150"
    )
    await manager.process_new_signal(
        user_id=1,
        broker_account_id=1,
        signal_data=signal_data,
        message_id="1001"
    )
    
    # Verify Trade
    from sqlalchemy import text
    result = await db_session.execute(
        text("SELECT status, entry_tolerance, entry_lower_bound, entry_upper_bound, entry_direction FROM trades")
    )
    trade = result.fetchone()
    
    assert trade.status == TradeState.WAITING_FOR_ENTRY.value
    assert trade.entry_tolerance == 1.5
    assert trade.entry_lower_bound == 148.5
    assert trade.entry_upper_bound == 151.5
    assert trade.entry_direction == "ABOVE"

@pytest.mark.parametrize("ltp, expected_triggered", [
    (148.4, False), # Below zone
    (148.5, True),  # On lower bound
    (150.0, True),  # Exact match
    (151.5, True),  # On upper bound
    (151.6, False), # Above zone
])
async def test_entry_tolerance_trigger(db_session, setup_10d_env, ltp, expected_triggered):
    manager, broker, settings = setup_10d_env
    
    # Insert pre-existing WAITING_FOR_ENTRY trade
    db_trade = Trade(
        user_id=1,
        signal_id=1,
        broker_account_id=broker.id,
        status=TradeState.WAITING_FOR_ENTRY,
        instrument_token=12345,
        quantity=0,
        entry_timeout_minutes=15,
        entry_expires_at=datetime.now(timezone.utc) + timedelta(minutes=15),
        entry_tolerance=1.5,
        entry_lower_bound=148.5,
        entry_upper_bound=151.5,
        entry_direction="ABOVE"
    )
    
    db_signal = Signal(
        id=1,
        message_id=1001,
        underlying="BANKNIFTY",
        strike="45000",
        option_type="CE",
        entry_trigger=150.0,
        stop_loss=120.0,
        target=200.0
    )
    
    db_session.add(db_signal)
    db_session.add(db_trade)
    await db_session.flush()

    # Simulate price update
    market_data_service.update_tick("12345", ltp)
    await manager.evaluate_market_prices("12345", ltp)

    await db_session.refresh(db_trade)
    if expected_triggered:
        assert db_trade.status == TradeState.POSITION_OPEN
        assert db_trade.actual_trigger_ltp == ltp
        assert db_trade.actual_triggered_at is not None
    else:
        assert db_trade.status == TradeState.WAITING_FOR_ENTRY
        assert db_trade.actual_trigger_ltp is None
        assert db_trade.actual_triggered_at is None
