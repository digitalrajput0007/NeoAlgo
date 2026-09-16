import pytest
import pytest_asyncio
import math
from decimal import Decimal
from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, patch

from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession

from app.trading.trade_manager import TradeManager
from app.database.models import Trade, Signal, TradingSettings, BrokerAccount, TradeState, Position, AuditLog
from app.database.models import Base

pytestmark = pytest.mark.asyncio

TEST_DB_FILE = "test_phase10f.db"
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

class MockBroker:
    def __init__(self):
        self.orders = []

    async def place_order(self, params):
        self.orders.append(params)
        return {
            "order_id": f"mock_{len(self.orders)}",
            "status": "COMPLETE",
            "price": params["price"]
        }

    async def resolve_option_contract(self, underlying, strike, option_type, expiry):
        return {"instrument_token": "mock_token"}

@pytest_asyncio.fixture
def mock_market_data():
    with patch("app.services.market_data_service.market_data_service.subscriptions", {}) as subs:
        yield subs

@pytest_asyncio.fixture
async def setup_data(db_session):
    account = BrokerAccount(user_id=1, broker_name="KotakNeo")
    db_session.add(account)
    settings = TradingSettings(
        user_id=1,
        new_trades_paused=False,
        max_daily_loss=5000,
        max_risk_per_trade=1000,
        max_trades_per_day=5,
        max_simultaneous_positions=2,
        entry_timeout_minutes=15,
        entry_tolerance=1.0
    )
    db_session.add(settings)
    await db_session.commit()
    return account, settings

class DummySignalData:
    def __init__(self, entry_trigger=100, stop_loss=90, target=120):
        self.underlying = "NIFTY"
        self.strike = 25000
        self.option_type = "CE"
        self.expiry = datetime.now(timezone.utc)
        self.entry_trigger = entry_trigger
        self.stop_loss = stop_loss
        self.target = target
        self.telegram_cmp = 98

async def test_new_signal_rejected_when_paused(db_session, setup_data):
    account, settings = setup_data
    settings.new_trades_paused = True
    db_session.add(settings)
    await db_session.commit()

    manager = TradeManager(db_session, MockBroker())
    trade = await manager.process_new_signal(1, account.id, DummySignalData(), 1)
    
    assert trade.status == TradeState.REJECTED
    
    from sqlalchemy import select
    log = (await db_session.execute(select(AuditLog).where(AuditLog.action == "RISK_REJECTED"))).scalars().first()
    assert log is not None
    assert log.details["reason"] == "NEW_TRADES_PAUSED"

async def test_cancel_waiting_signals(db_session, setup_data):
    account, _ = setup_data
    trade1 = Trade(user_id=1, broker_account_id=account.id, status=TradeState.WAITING_FOR_ENTRY, instrument_token="tok1")
    trade2 = Trade(user_id=1, broker_account_id=account.id, status=TradeState.POSITION_OPEN, instrument_token="tok2")
    db_session.add_all([trade1, trade2])
    await db_session.commit()

    manager = TradeManager(db_session, MockBroker())
    count = await manager.cancel_waiting_signals()
    assert count == 1
    
    await db_session.refresh(trade1)
    await db_session.refresh(trade2)
    assert trade1.status == TradeState.CANCELLED
    assert trade1.cancel_reason == "MANUAL_CANCEL_WAITING"
    assert trade2.status == TradeState.POSITION_OPEN

async def test_emergency_close_all_paper_positions(db_session, setup_data, mock_market_data):
    account, _ = setup_data
    trade1 = Trade(user_id=1, broker_account_id=account.id, status=TradeState.POSITION_OPEN, instrument_token="tok1", quantity=75)
    trade2 = Trade(user_id=1, broker_account_id=account.id, status=TradeState.PARTIAL_PROFIT, instrument_token="tok2", quantity=25)
    # Trade 3 has invalid LTP
    trade3 = Trade(user_id=1, broker_account_id=account.id, status=TradeState.POSITION_OPEN, instrument_token="tok3", quantity=50)
    db_session.add_all([trade1, trade2, trade3])
    await db_session.commit()

    mock_market_data["tok1"] = {"latest_ltp": 150}
    mock_market_data["tok2"] = {"latest_ltp": 160}
    mock_market_data["tok3"] = {"latest_ltp": 0} # Invalid

    broker = MockBroker()
    manager = TradeManager(db_session, broker)
    result = await manager.emergency_close_all_paper_positions()
    
    assert result["closed_positions"] == 2
    assert result["failed_positions"] == 1
    
    await db_session.refresh(trade1)
    await db_session.refresh(trade2)
    await db_session.refresh(trade3)
    
    assert trade1.status == TradeState.CLOSED
    assert trade2.status == TradeState.CLOSED
    assert trade3.status == TradeState.POSITION_OPEN
    
    assert len(broker.orders) == 2
    assert broker.orders[0]["instrument_token"] == "tok1"
    assert broker.orders[0]["price"] == 150
    assert broker.orders[1]["instrument_token"] == "tok2"
    assert broker.orders[1]["price"] == 160

async def test_emergency_close_idempotent(db_session, setup_data, mock_market_data):
    account, _ = setup_data
    trade1 = Trade(user_id=1, broker_account_id=account.id, status=TradeState.POSITION_OPEN, instrument_token="tok1", quantity=75)
    db_session.add(trade1)
    await db_session.commit()
    
    mock_market_data["tok1"] = {"latest_ltp": 150}
    
    broker = MockBroker()
    manager = TradeManager(db_session, broker)
    
    # First call
    result1 = await manager.emergency_close_all_paper_positions()
    assert result1["closed_positions"] == 1
    assert len(broker.orders) == 1
    
    # Second call
    result2 = await manager.emergency_close_all_paper_positions()
    assert result2["closed_positions"] == 0
    assert len(broker.orders) == 1 # still 1 order


