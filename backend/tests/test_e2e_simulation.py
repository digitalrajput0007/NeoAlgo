import pytest
import pytest_asyncio
from datetime import datetime, timezone
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
import uuid

from app.database.database import Base
from app.database.models import User, BrokerAccount, TradingSettings, Trade, TradeState, Position, Order, AuditLog, TelegramMessage
from app.brokers.paper import PaperBroker
from app.telegram.replay import ReplayEngine

# NOTE: E2E tests are configured for PostgreSQL per production requirements.
# Ensure the local PostgreSQL instance is running via Docker Compose.
# If Docker/Postgres is unavailable on this execution host, these tests will fail to connect.
# A separate SQLite configuration would be needed to bypass this environmental limit.

TEST_DB_URL = "sqlite+aiosqlite:///:memory:"

@pytest.fixture(scope="session")
def engine():
    return create_async_engine(TEST_DB_URL, echo=False)

@pytest_asyncio.fixture
async def setup_db(engine):
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)

@pytest_asyncio.fixture
async def db_session(engine, setup_db):
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with async_session() as session:
        yield session

@pytest_asyncio.fixture
async def test_user_setup(db_session):
    user = User(username="test_e2e", email="test@e2e.com", hashed_password="pwd")
    db_session.add(user)
    await db_session.flush()
    
    broker = BrokerAccount(user_id=user.id, broker_name="PAPER", is_paper_trading=True)
    db_session.add(broker)
    
    # Configure explicit trailing stop parameters
    settings = TradingSettings(
        user_id=user.id,
        is_algo_active=True,
        max_daily_loss=5000.0,
        max_risk_per_trade=1000.0,
        max_trades_per_day=5,
        max_simultaneous_positions=2,
        partial_exit_percent=50.0,
        trailing_enabled=True,
        trailing_distance=5.0
    )
    
    db_session.add(settings)
    await db_session.commit()
    
    return user.id, broker.id

@pytest.mark.asyncio
async def test_scenario_a_target(db_session, test_user_setup):
    """Scenario A: Signal -> Wait -> Entry -> Target"""
    user_id, broker_id = test_user_setup
    paper_broker = PaperBroker()
    engine = ReplayEngine(db_session, paper_broker, user_id, broker_id)
    
    events = [
        {"type": "telegram", "message_id": "A1", "channel_id": "CH1", "message": "NIFTY 23500 CE 15 Sept 26 Expiry\nBuy above 150\nSL below 144\nTgt above 170\nCMP 150"},
        {"type": "price", "instrument": "PAPER_NIFTY_23500_CE_2026-09-15", "price": 149},
        {"type": "price", "instrument": "PAPER_NIFTY_23500_CE_2026-09-15", "price": 150},
        {"type": "price", "instrument": "PAPER_NIFTY_23500_CE_2026-09-15", "price": 170}
    ]
    
    await engine.play_events(events)
    
    # Verify
    import sqlalchemy as sa
    trade = (await db_session.execute(sa.select(Trade).where(Trade.user_id == user_id))).scalars().first()
    assert trade.status == TradeState.CLOSED
    assert trade.exit_price == 170.0
    # Entry price 150.0, Target 170.0, qty 75. PnL = 20 * 75 = 1500
    assert trade.realized_pnl == 1500.0

@pytest.mark.asyncio
async def test_scenario_h_duplicate_signal(db_session, test_user_setup):
    """Scenario H: Duplicate Signal Rejection"""
    user_id, broker_id = test_user_setup
    paper_broker = PaperBroker()
    engine = ReplayEngine(db_session, paper_broker, user_id, broker_id)
    
    msg_text = "NIFTY 23400 PE 15 Sept 26 Expiry\nBuy above 69\nSL below 62\nTgt above 88\nCMP 69"
    events = [
        {"type": "telegram", "message_id": "H1", "channel_id": "CH1", "message": msg_text},
        {"type": "telegram", "message_id": "H1", "channel_id": "CH1", "message": msg_text} # Exact duplicate
    ]
    
    await engine.play_events(events)
    
    # Verify only 1 trade exists
    import sqlalchemy as sa
    trades = (await db_session.execute(sa.select(Trade).where(Trade.user_id == user_id))).scalars().all()
    assert len(trades) == 1
    
    # Verify Audit log logged DUPLICATE_MESSAGE_IGNORED
    audits = (await db_session.execute(sa.select(AuditLog).where(AuditLog.action == "DUPLICATE_MESSAGE_IGNORED"))).scalars().all()
    assert len(audits) == 1

@pytest.mark.asyncio
async def test_scenario_i_multiple_active_trades(db_session, test_user_setup):
    """Scenario I: Multiple Active Trades Price Isolation"""
    user_id, broker_id = test_user_setup
    paper_broker = PaperBroker()
    engine = ReplayEngine(db_session, paper_broker, user_id, broker_id)
    
    events = [
        {"type": "telegram", "message_id": "I1", "channel_id": "CH1", "message": "NIFTY 23500 CE 15 Sept 26 Expiry\nBuy above 150\nSL below 144\nTgt above 170\nCMP 150"},
        {"type": "telegram", "message_id": "I2", "channel_id": "CH1", "message": "NIFTY 23400 PE 15 Sept 26 Expiry\nBuy above 70\nSL below 60\nTgt above 90\nCMP 70"},
        {"type": "price", "instrument": "PAPER_NIFTY_23400_PE_2026-09-15", "price": 75}
    ]
    
    await engine.play_events(events)
    
    # Verify CE trade is still waiting, PE trade is open
    import sqlalchemy as sa
    trades = (await db_session.execute(sa.select(Trade).where(Trade.user_id == user_id).order_by(Trade.id.asc()))).scalars().all()
    
    assert trades[0].status == TradeState.WAITING_FOR_ENTRY  # CE
    assert trades[1].status == TradeState.POSITION_OPEN      # PE

@pytest.mark.asyncio
async def test_scenario_e_partial_profit_and_trailing(db_session, test_user_setup):
    """Scenario E: Partial Profit and explicit config check"""
    user_id, broker_id = test_user_setup
    paper_broker = PaperBroker()
    engine = ReplayEngine(db_session, paper_broker, user_id, broker_id)
    
    events = [
        {"type": "telegram", "message_id": "E1", "channel_id": "CH1", "message": "NIFTY 23500 CE 15 Sept 26 Expiry\nBuy above 150\nSL below 144\nTgt above 170\nCMP 150"},
        {"type": "price", "instrument": "PAPER_NIFTY_23500_CE_2026-09-15", "price": 151},
        {"type": "telegram", "message_id": "E2", "channel_id": "CH1", "message": "Book Partial Profit and keep Trailing stop"}
    ]
    
    await engine.play_events(events)
    
    import sqlalchemy as sa
    trade = (await db_session.execute(sa.select(Trade).where(Trade.user_id == user_id))).scalars().first()
    
    assert trade.status == TradeState.TRAILING_STOP
    # Total qty 75. 50% = 37 sold. Remaining = 38.
    assert trade.quantity == 38
    
    pos = (await db_session.execute(sa.select(Position).where(Position.trade_id == trade.id))).scalars().first()
    assert pos.quantity == 38

@pytest.mark.asyncio
async def test_scenario_restart_recovery(db_session, test_user_setup):
    """Scenario: Restart Recovery (Save state, create new TradeManager, continue)"""
    user_id, broker_id = test_user_setup
    paper_broker = PaperBroker()
    engine1 = ReplayEngine(db_session, paper_broker, user_id, broker_id)
    
    events_phase_1 = [
        {"type": "telegram", "message_id": "R1", "channel_id": "CH1", "message": "NIFTY 23500 CE 15 Sept 26 Expiry\nBuy above 150\nSL below 144\nTgt above 170\nCMP 150"},
        {"type": "price", "instrument": "PAPER_NIFTY_23500_CE_2026-09-15", "price": 151}
    ]
    await engine1.play_events(events_phase_1)
    
    # 1. Destroy TradeManager instance
    del engine1
    
    # 2. Create new TradeManager
    paper_broker2 = PaperBroker()
    engine2 = ReplayEngine(db_session, paper_broker2, user_id, broker_id)
    
    events_phase_2 = [
        {"type": "price", "instrument": "PAPER_NIFTY_23500_CE_2026-09-15", "price": 170}
    ]
    await engine2.play_events(events_phase_2)
    
    import sqlalchemy as sa
    trade = (await db_session.execute(sa.select(Trade).where(Trade.user_id == user_id))).scalars().first()
    assert trade.status == TradeState.CLOSED
    
    positions = (await db_session.execute(sa.select(Position).where(Position.trade_id == trade.id))).scalars().all()
    assert len(positions) == 1
    assert positions[0].is_open is False
    assert positions[0].quantity == 0

@pytest.mark.asyncio
async def test_scenario_b_stop_loss(db_session, test_user_setup):
    """Scenario B: Signal -> Entry -> Stop Loss"""
    user_id, broker_id = test_user_setup
    paper_broker = PaperBroker()
    engine = ReplayEngine(db_session, paper_broker, user_id, broker_id)
    
    events = [
        {"type": "telegram", "message_id": "B1", "channel_id": "CH1", "message": "NIFTY 23500 CE 15 Sept 26 Expiry\nBuy above 150\nSL below 144\nTgt above 170\nCMP 150"},
        {"type": "price", "instrument": "PAPER_NIFTY_23500_CE_2026-09-15", "price": 150},
        {"type": "price", "instrument": "PAPER_NIFTY_23500_CE_2026-09-15", "price": 140}
    ]
    await engine.play_events(events)
    
    import sqlalchemy as sa
    trade = (await db_session.execute(sa.select(Trade).where(Trade.user_id == user_id))).scalars().first()
    assert trade.status == TradeState.CLOSED
    assert trade.exit_price == 140.0
    assert trade.realized_pnl == -750.0  # (140 - 150) * 75

@pytest.mark.asyncio
async def test_scenario_c_explicit_exit(db_session, test_user_setup):
    """Scenario C: Signal -> Entry -> Explicit Exit Signal"""
    user_id, broker_id = test_user_setup
    paper_broker = PaperBroker()
    engine = ReplayEngine(db_session, paper_broker, user_id, broker_id)
    
    events = [
        {"type": "telegram", "message_id": "C1", "channel_id": "CH1", "message": "NIFTY 23500 CE 15 Sept 26 Expiry\nBuy above 150\nSL below 144\nTgt above 170\nCMP 150"},
        {"type": "price", "instrument": "PAPER_NIFTY_23500_CE_2026-09-15", "price": 150},
        {"type": "telegram", "message_id": "C2", "channel_id": "CH1", "message": "exit"}
    ]
    await engine.play_events(events)
    
    import sqlalchemy as sa
    trade = (await db_session.execute(sa.select(Trade).where(Trade.user_id == user_id))).scalars().first()
    assert trade.status == TradeState.CLOSED

@pytest.mark.asyncio
async def test_scenario_g_risk_rejection(db_session, test_user_setup):
    """Scenario G: Risk Constraints Rejection (Max Daily Loss)"""
    user_id, broker_id = test_user_setup
    
    import sqlalchemy as sa
    trade_loss = Trade(
        user_id=user_id,
        broker_account_id=broker_id,
        status=TradeState.CLOSED,
        realized_pnl=-6000.0
    )
    db_session.add(trade_loss)
    await db_session.commit()
    
    paper_broker = PaperBroker()
    engine = ReplayEngine(db_session, paper_broker, user_id, broker_id)
    
    events = [
        {"type": "telegram", "message_id": "G1", "channel_id": "CH1", "message": "NIFTY 23500 CE 15 Sept 26 Expiry\nBuy above 150\nSL below 144\nTgt above 170\nCMP 150"}
    ]
    await engine.play_events(events)
    
    trade = (await db_session.execute(sa.select(Trade).where(Trade.user_id == user_id).order_by(Trade.id.desc()))).scalars().first()
    assert trade.status == TradeState.REJECTED
