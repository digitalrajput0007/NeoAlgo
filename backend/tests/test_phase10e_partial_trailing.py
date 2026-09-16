import pytest
import pytest_asyncio
import os
import math
from decimal import Decimal
from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, patch

from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession

from app.trading.trade_manager import TradeManager
from app.database.models import Trade, Signal, TradingSettings, BrokerAccount, TradeState, Position
from app.database.models import Base

pytestmark = pytest.mark.asyncio

TEST_DB_FILE = "test_phase10e.db"
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
async def manager_env(db_session):
    # Mock broker
    broker = AsyncMock()
    # Mock Risk Manager
    risk_manager = AsyncMock()
    
    # Paper Broker Account
    acc = BrokerAccount(
        user_id=1,
        broker_name="paper",
        is_paper_trading=True
    )
    db_session.add(acc)
    
    # Settings
    settings = TradingSettings(
        user_id=1,
        partial_profit_enabled=True,
        partial_profit_trigger=10.0,
        partial_profit_percentage=50.0,
        trailing_stop_enabled=True,
        trailing_activation_mode="AFTER_PARTIAL_PROFIT",
        trailing_activation_profit=10.0,
        trailing_distance=5.0
    )
    db_session.add(settings)
    
    # Signal
    signal = Signal(
        message_id=1,
        underlying="NIFTY",
        strike=25000,
        option_type="CE",
        expiry="2024-10-31",
        entry_trigger=140.0,
        stop_loss=100.0,
        target=200.0,
        created_at=datetime.now(timezone.utc)
    )
    db_session.add(signal)
    await db_session.flush()
    
    trade = Trade(
        user_id=1,
        signal_id=signal.id,
        broker_account_id=acc.id,
        status=TradeState.POSITION_OPEN,
        instrument_token="NIFTY24OCT25000CE",
        quantity=75,
        entry_price=140.0,
        partial_profit_enabled=True,
        partial_profit_trigger=10.0,
        partial_profit_percentage=50.0,
        partial_profit_taken=False,
        trailing_stop_enabled=True,
        trailing_activation_mode="AFTER_PARTIAL_PROFIT",
        trailing_activation_profit=10.0,
        trailing_distance=5.0,
        trailing_active=False
    )
    db_session.add(trade)
    
    position = Position(
        user_id=1,
        trade_id=1,
        broker_account_id=acc.id,
        instrument_token="NIFTY24OCT25000CE",
        quantity=75,
        average_price=140.0,
        is_open=True
    )
    db_session.add(position)
    await db_session.commit()
    
    manager = TradeManager(db_session, broker)
    manager.risk_manager = risk_manager
    manager._place_paper_order = AsyncMock()
    return manager, trade

async def test_partial_profit_and_trailing(db_session, manager_env):
    manager, trade = manager_env
    
    # Tick 1: Reaches partial profit trigger (140 + 10 = 150)
    await manager.evaluate_market_prices("NIFTY24OCT25000CE", 151.0)
    
    await db_session.refresh(trade)
    assert trade.status == TradeState.TRAILING_STOP
    assert trade.partial_profit_taken == True
    assert trade.quantity == 75 - math.floor(75 * 0.5) # 38
    
    # Tick 2: Trailing stop should be active now (AFTER_PARTIAL_PROFIT)
    # Highest LTP should be 151. Trailing stop should be 151 - 5 = 146
    assert trade.trailing_active == True
    assert trade.highest_ltp == 151.0
    assert trade.trailing_stop == 146.0

    # Tick 3: LTP goes up to 155, trailing stop moves up
    await manager.evaluate_market_prices("NIFTY24OCT25000CE", 155.0)
    await db_session.refresh(trade)
    assert trade.highest_ltp == 155.0
    assert trade.trailing_stop == 150.0

    # Tick 4: LTP goes down to 152, trailing stop DOES NOT move
    await manager.evaluate_market_prices("NIFTY24OCT25000CE", 152.0)
    await db_session.refresh(trade)
    assert trade.highest_ltp == 155.0
    assert trade.trailing_stop == 150.0

    # Tick 5: LTP goes to 149, triggering trailing stop
    await manager.evaluate_market_prices("NIFTY24OCT25000CE", 149.0)
    await db_session.refresh(trade)
    assert trade.status == TradeState.CLOSED
    assert trade.quantity == 0 # Closed remaining 38
