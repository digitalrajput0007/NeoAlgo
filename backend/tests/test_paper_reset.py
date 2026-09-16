import os
import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from datetime import datetime, timezone, timedelta
from unittest.mock import patch, MagicMock

from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy import event
from sqlalchemy.pool import NullPool
from sqlalchemy.future import select

TEST_DB_FILE = "test_paper_reset.db"
TEST_DB_URL = f"sqlite+aiosqlite:///./{TEST_DB_FILE}"

if os.path.exists(TEST_DB_FILE):
    try:
        os.remove(TEST_DB_FILE)
    except Exception:
        pass

test_engine = create_async_engine(
    TEST_DB_URL,
    poolclass=NullPool,
    connect_args={"timeout": 30.0},
    echo=False,
)

@event.listens_for(test_engine.sync_engine, "connect")
def set_sqlite_pragma(dbapi_connection, connection_record):
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA busy_timeout=30000")
    cursor.close()

TestAsyncSessionLocal = async_sessionmaker(
    test_engine, class_=AsyncSession, expire_on_commit=False
)

import app.database.database as db_mod
import app.services.telegram_listener as tel_mod
import app.api.routes.dashboard as dash_mod
from app.database.models import (
    Base, User, BrokerAccount, TradingSettings, Trade, TradeState, Signal, Order, Position, AuditLog
)

db_mod.engine = test_engine
db_mod.AsyncSessionLocal = TestAsyncSessionLocal
tel_mod.AsyncSessionLocal = TestAsyncSessionLocal
dash_mod.AsyncSessionLocal = TestAsyncSessionLocal

from app.main import app
from app.database.database import get_db
from app.config import settings
from app.brokers.kotak_neo import KotakNeoBroker
from app.trading.risk_manager import RiskManager

async def override_get_db():
    async with TestAsyncSessionLocal() as session:
        yield session

@pytest_asyncio.fixture(scope="function", autouse=True)
async def setup_test_database():
    """Setup clean tables and seed default accounts before each test."""
    app.dependency_overrides[get_db] = override_get_db
    dash_mod.AsyncSessionLocal = TestAsyncSessionLocal
    db_mod.AsyncSessionLocal = TestAsyncSessionLocal

    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)

    async with TestAsyncSessionLocal() as session:
        user = User(id=1, username="test_trader", email="trader@test.com", hashed_password="pw")
        session.add(user)

        paper_account = BrokerAccount(
            id=1,
            user_id=1,
            broker_name="PAPER",
            is_paper_trading=True,
            paper_session_id="INITIAL_TEST_SESSION",
            paper_reset_at=None
        )
        session.add(paper_account)

        live_account = BrokerAccount(
            id=2,
            user_id=1,
            broker_name="KOTAK_NEO",
            is_paper_trading=False
        )
        session.add(live_account)

        settings_record = TradingSettings(
            user_id=1,
            max_daily_loss=5000.0,
            max_trades_per_day=10,
            max_simultaneous_positions=2,
            is_algo_active=True
        )
        session.add(settings_record)
        await session.commit()

    yield

    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    app.dependency_overrides.pop(get_db, None)


# =========================================================================
# 15 REQUIREMENT-SPECIFIC TESTS FOR SAFE PAPER RESET & SESSION BOUNDARY
# =========================================================================

@pytest.mark.asyncio
async def test_01_existing_historical_paper_profit_remains_in_records():
    """Requirement 1: Existing historical paper profit remains preserved in historical records."""
    earlier = datetime.now(timezone.utc) - timedelta(hours=2)
    async with TestAsyncSessionLocal() as session:
        t1 = Trade(
            id=1,
            user_id=1,
            broker_account_id=1,
            status=TradeState.CLOSED,
            instrument_token="PAPER_NIFTY_23500_CE",
            quantity=75,
            entry_price=152.0,
            exit_price=171.0,
            realized_pnl=1425.0,
            created_at=earlier,
            updated_at=earlier
        )
        session.add(t1)
        await session.commit()

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Perform reset
        res = await client.post("/api/paper/reset")
        assert res.status_code == 200

        # Check historical trade in DB directly
        async with TestAsyncSessionLocal() as session:
            t1_after = await session.get(Trade, 1)
            assert t1_after is not None
            assert t1_after.realized_pnl == 1425.0
            assert t1_after.entry_price == 152.0
            assert t1_after.exit_price == 171.0

        # Check summary endpoint exposes historical_today_pnl
        sum_res = await client.get("/api/dashboard/summary")
        assert sum_res.status_code == 200
        data = sum_res.json()
        assert data["metrics"]["historical_today_pnl"] == 1425.0


@pytest.mark.asyncio
async def test_02_paper_reset_starts_new_paper_session():
    """Requirement 2: Paper reset starts a new paper session with a new session identifier."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        res = await client.post("/api/paper/reset")
        assert res.status_code == 200
        data = res.json()
        assert data["status"] == "SUCCESS"
        assert "SESSION_" in data["session_id"]
        assert data["previous_session_id"] == "INITIAL_TEST_SESSION"

        # Verify BrokerAccount is updated with the new session ID
        async with TestAsyncSessionLocal() as session:
            broker = await session.get(BrokerAccount, 1)
            assert broker.paper_session_id == data["session_id"]
            assert broker.paper_reset_at is not None


@pytest.mark.asyncio
async def test_03_current_paper_session_pnl_is_zero_immediately_after_reset():
    """Requirement 3: Current paper-session P&L = 0 immediately after reset."""
    # Seed historical trade with profit
    earlier = datetime.now(timezone.utc) - timedelta(hours=1)
    async with TestAsyncSessionLocal() as session:
        t = Trade(
            id=1, user_id=1, broker_account_id=1, status=TradeState.CLOSED,
            instrument_token="PAPER_NIFTY_23500_CE", quantity=75,
            entry_price=150.0, exit_price=160.0, realized_pnl=750.0,
            created_at=earlier, updated_at=earlier
        )
        session.add(t)
        await session.commit()

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        await client.post("/api/paper/reset")
        sum_res = await client.get("/api/dashboard/summary")
        assert sum_res.status_code == 200
        metrics = sum_res.json()["metrics"]
        assert metrics["current_session_pnl"] == 0.0
        assert metrics["today_pnl"] == 0.0
        assert metrics["historical_today_pnl"] == 750.0


@pytest.mark.asyncio
async def test_04_old_trades_do_not_contribute_to_new_session_pnl():
    """Requirement 4: Old trades before reset do NOT contribute to new session P&L."""
    earlier = datetime.now(timezone.utc) - timedelta(minutes=30)
    async with TestAsyncSessionLocal() as session:
        t1 = Trade(
            id=1, user_id=1, broker_account_id=1, status=TradeState.CLOSED,
            instrument_token="INST1", quantity=75, entry_price=100.0,
            exit_price=120.0, realized_pnl=1500.0,
            created_at=earlier, updated_at=earlier
        )
        session.add(t1)
        await session.commit()

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        await client.post("/api/paper/reset")
        res = await client.get("/api/dashboard/summary")
        metrics = res.json()["metrics"]
        assert metrics["current_session_pnl"] == 0.0
        assert metrics["historical_today_pnl"] == 1500.0


@pytest.mark.asyncio
async def test_05_new_paper_trade_pnl_contributes_to_new_session_pnl():
    """Requirement 5: New paper trade P&L created after reset contributes to new session P&L."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Reset starts session
        reset_res = await client.post("/api/paper/reset")
        assert reset_res.status_code == 200

        # Create a new trade in current session
        now = datetime.now(timezone.utc) + timedelta(seconds=2)
        async with TestAsyncSessionLocal() as session:
            new_trade = Trade(
                id=99, user_id=1, broker_account_id=1, status=TradeState.CLOSED,
                instrument_token="NEW_PAPER_INST", quantity=50,
                entry_price=100.0, exit_price=110.0, realized_pnl=500.0,
                created_at=now, updated_at=now
            )
            session.add(new_trade)
            await session.commit()

        # Check summary reflects the new session trade P&L
        res = await client.get("/api/dashboard/summary")
        metrics = res.json()["metrics"]
        assert metrics["current_session_pnl"] == 500.0
        assert metrics["historical_today_pnl"] == 500.0


@pytest.mark.asyncio
async def test_06_reset_does_not_create_artificial_pnl():
    """Requirement 6: Reset does NOT create artificial P&L when closing positions."""
    async with TestAsyncSessionLocal() as session:
        tr = Trade(
            id=5, user_id=1, broker_account_id=1, status=TradeState.POSITION_OPEN,
            instrument_token="INST5", quantity=75, entry_price=150.0, realized_pnl=0.0
        )
        pos = Position(
            id=5, user_id=1, trade_id=5, broker_account_id=1,
            instrument_token="INST5", quantity=75, average_price=150.0, is_open=True
        )
        session.add(tr)
        session.add(pos)
        await session.commit()

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        await client.post("/api/paper/reset")

    async with TestAsyncSessionLocal() as session:
        tr_after = await session.get(Trade, 5)
        assert tr_after.realized_pnl == 0.0


@pytest.mark.asyncio
async def test_07_reset_does_not_assign_fake_exit_prices():
    """Requirement 7: Reset does NOT assign fake/arbitrary exit prices to unclosed positions."""
    async with TestAsyncSessionLocal() as session:
        tr = Trade(
            id=7, user_id=1, broker_account_id=1, status=TradeState.POSITION_OPEN,
            instrument_token="INST7", quantity=75, entry_price=150.0, exit_price=None
        )
        pos = Position(
            id=7, user_id=1, trade_id=7, broker_account_id=1,
            instrument_token="INST7", quantity=75, average_price=150.0, is_open=True
        )
        session.add(tr)
        session.add(pos)
        await session.commit()

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        await client.post("/api/paper/reset")

    async with TestAsyncSessionLocal() as session:
        tr_after = await session.get(Trade, 7)
        assert tr_after.exit_price is None
        assert tr_after.entry_price == 150.0


@pytest.mark.asyncio
async def test_08_historical_trades_remain_available():
    """Requirement 8: Historical trades remain available and accessible in the database."""
    async with TestAsyncSessionLocal() as session:
        for i in range(1, 4):
            t = Trade(id=i, user_id=1, broker_account_id=1, status=TradeState.POSITION_OPEN, instrument_token=f"T_{i}")
            session.add(t)
        await session.commit()

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        await client.post("/api/paper/reset")

    async with TestAsyncSessionLocal() as session:
        stmt = select(Trade)
        trades = (await session.execute(stmt)).scalars().all()
        assert len(trades) == 3


@pytest.mark.asyncio
async def test_09_historical_orders_remain_available():
    """Requirement 9: Historical orders remain preserved while current session orders is 0."""
    earlier = datetime.now(timezone.utc) - timedelta(hours=1)
    async with TestAsyncSessionLocal() as session:
        for i in range(1, 4):
            o = Order(
                id=i, trade_id=None, broker_order_id=f"ORD_{i}",
                order_type="BUY", quantity=75, price=100.0, status="FILLED",
                created_at=earlier
            )
            session.add(o)
        await session.commit()

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        await client.post("/api/paper/reset")
        sum_res = await client.get("/api/dashboard/summary")
        metrics = sum_res.json()["metrics"]
        assert metrics["current_session_orders"] == 0
        assert metrics["historical_orders_today"] == 3


@pytest.mark.asyncio
async def test_10_signals_remain_available():
    """Requirement 10: Ingestion signals remain preserved and are not deleted."""
    earlier = datetime.now(timezone.utc) - timedelta(hours=1)
    async with TestAsyncSessionLocal() as session:
        sig = Signal(
            id=1, underlying="NIFTY", strike=23500.0, option_type="CE",
            expiry="2026-09-17", entry_trigger=150.0, stop_loss=130.0,
            target=180.0, telegram_cmp=150.0, created_at=earlier
        )
        session.add(sig)
        await session.commit()

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        await client.post("/api/paper/reset")
        sum_res = await client.get("/api/dashboard/summary")
        metrics = sum_res.json()["metrics"]
        assert metrics["signals_today"] == 1
        assert metrics["current_session_signals"] == 0


@pytest.mark.asyncio
async def test_11_open_positions_after_reset_is_zero():
    """Requirement 11: Open positions count after reset equals 0."""
    async with TestAsyncSessionLocal() as session:
        for i in range(1, 3):
            pos = Position(
                id=i, user_id=1, trade_id=i, broker_account_id=1,
                instrument_token=f"INST_{i}", quantity=75, average_price=100.0, is_open=True
            )
            session.add(pos)
        await session.commit()

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        res = await client.post("/api/paper/reset")
        assert res.json()["open_positions_before_reset"] == 2
        assert res.json()["positions_reset"] == 2

        sum_res = await client.get("/api/dashboard/summary")
        assert sum_res.json()["metrics"]["open_positions"] == 0


@pytest.mark.asyncio
async def test_12_active_trades_after_reset_is_zero():
    """Requirement 12: Active trades count after reset equals 0."""
    async with TestAsyncSessionLocal() as session:
        t = Trade(id=1, user_id=1, broker_account_id=1, status=TradeState.POSITION_OPEN, instrument_token="INST1")
        session.add(t)
        await session.commit()

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        await client.post("/api/paper/reset")
        sum_res = await client.get("/api/dashboard/summary")
        assert sum_res.json()["metrics"]["active_trades"] == 0


@pytest.mark.asyncio
async def test_13_risk_simultaneous_positions_is_zero():
    """Requirement 13: Risk Manager unblocked - simultaneous position count is 0."""
    async with TestAsyncSessionLocal() as session:
        t1 = Trade(id=1, user_id=1, broker_account_id=1, status=TradeState.POSITION_OPEN, instrument_token="T1", quantity=75)
        t2 = Trade(id=2, user_id=1, broker_account_id=1, status=TradeState.POSITION_OPEN, instrument_token="T2", quantity=75)
        session.add_all([t1, t2])
        await session.commit()

        # Before reset: Limit (2) is reached
        rm = RiskManager(session)
        allowed, reason = await rm.check_new_trade_allowed(user_id=1)
        assert allowed is False
        assert reason == "MAX_SIMULTANEOUS_POSITIONS_EXCEEDED"

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        await client.post("/api/paper/reset")

    # After reset: Allowed
    async with TestAsyncSessionLocal() as session:
        rm = RiskManager(session)
        allowed, reason = await rm.check_new_trade_allowed(user_id=1)
        assert allowed is True
        assert reason == "OK"


@pytest.mark.asyncio
async def test_14_no_live_broker_apis_invoked():
    """Requirement 14: No live broker order or exit APIs are invoked during reset."""
    with patch.object(KotakNeoBroker, "place_order", MagicMock()) as mock_place, \
         patch.object(KotakNeoBroker, "exit_position", MagicMock()) as mock_exit, \
         patch.object(KotakNeoBroker, "cancel_order", MagicMock()) as mock_cancel:

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            res = await client.post("/api/paper/reset")
            assert res.status_code == 200

            mock_place.assert_not_called()
            mock_exit.assert_not_called()
            mock_cancel.assert_not_called()


@pytest.mark.asyncio
async def test_15_live_orders_remain_disabled():
    """Requirement 15: LIVE ORDERS remain DISABLED and mode remains PAPER."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        res = await client.get("/api/dashboard/summary")
        assert res.status_code == 200
        data = res.json()
        assert data["mode"] == "PAPER"
        assert data["live_orders"] == "DISABLED"


@pytest.mark.asyncio
async def test_16_scoped_trades_query_semantics():
    """Requirement 16: Active trades query returns 0, historical trades query returns closed trades."""
    async with TestAsyncSessionLocal() as session:
        for i in range(1, 4):
            t = Trade(id=i, user_id=1, broker_account_id=1, status=TradeState.POSITION_OPEN, instrument_token=f"INST_{i}")
            session.add(t)
        await session.commit()

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Before reset: 3 active
        res_before = await client.get("/api/trades?scope=active")
        assert len(res_before.json()) == 3

        # Execute paper reset
        await client.post("/api/paper/reset")

        # After reset: default / scope=active returns 0
        res_default = await client.get("/api/trades")
        assert len(res_default.json()) == 0

        res_active = await client.get("/api/trades?scope=active")
        assert len(res_active.json()) == 0

        # Scope=history returns the 3 trades, and all remain CLOSED
        res_hist = await client.get("/api/trades?scope=history")
        hist_trades = res_hist.json()
        assert len(hist_trades) == 3
        for ht in hist_trades:
            assert ht["status"] == "CLOSED"


@pytest.mark.asyncio
async def test_17_scoped_positions_query_semantics():
    """Requirement 17: Open positions query returns 0, historical positions do not appear in open positions."""
    async with TestAsyncSessionLocal() as session:
        for i in range(1, 4):
            pos = Position(
                id=i, user_id=1, trade_id=i, broker_account_id=1,
                instrument_token=f"INST_{i}", quantity=75, average_price=120.0, is_open=True
            )
            session.add(pos)
        await session.commit()

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Before reset: 3 open positions
        res_before = await client.get("/api/positions?scope=open")
        assert len(res_before.json()) == 3

        # Execute paper reset
        await client.post("/api/paper/reset")

        # After reset: default / scope=open returns ZERO open positions
        res_default = await client.get("/api/positions")
        assert len(res_default.json()) == 0

        res_open = await client.get("/api/positions?scope=open")
        assert len(res_open.json()) == 0

        # Scope=history returns all 3 closed positions
        res_hist = await client.get("/api/positions?scope=history")
        hist_positions = res_hist.json()
        assert len(hist_positions) == 3
        for hp in hist_positions:
            assert hp["is_open"] is False


@pytest.mark.asyncio
async def test_18_scoped_orders_query_semantics():
    """Requirement 18: Current session orders returns 0 after reset, historical orders preserved."""
    earlier = datetime.now(timezone.utc) - timedelta(hours=2)
    async with TestAsyncSessionLocal() as session:
        for i in range(1, 4):
            o = Order(
                id=i, trade_id=None, broker_order_id=f"HIST_ORD_{i}",
                order_type="BUY", quantity=75, price=100.0, status="FILLED",
                created_at=earlier
            )
            session.add(o)
        await session.commit()

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Execute paper reset
        await client.post("/api/paper/reset")

        # Default / scope=current_session returns ZERO orders
        res_default = await client.get("/api/orders")
        assert len(res_default.json()) == 0

        res_curr = await client.get("/api/orders?scope=current_session")
        assert len(res_curr.json()) == 0

        # Scope=history returns the 3 historical orders
        res_hist = await client.get("/api/orders?scope=history")
        assert len(res_hist.json()) == 3


@pytest.mark.asyncio
async def test_19_audit_logs_preserved_after_reset():
    """Requirement 19: PAPER_STATE_RESET is logged, audit logs remain intact."""
    async with TestAsyncSessionLocal() as session:
        log1 = AuditLog(
            action="PRE_TEST_ACTION",
            details="Prior action before reset",
            created_at=datetime.now(timezone.utc) - timedelta(hours=1)
        )
        session.add(log1)
        await session.commit()

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        await client.post("/api/paper/reset")

        res = await client.get("/api/audit-logs")
        logs = res.json()
        actions = [l["event"] for l in logs]
        assert "PAPER_STATE_RESET" in actions
        assert "PRE_TEST_ACTION" in actions


@pytest.mark.asyncio
async def test_20_navigation_badge_counts_reflect_current_state():
    """Requirement 20: Dashboard metrics used by navigation badges reflect current state counts."""
    async with TestAsyncSessionLocal() as session:
        # Seed 1 trade, 1 position, 1 order, 1 signal
        t = Trade(id=1, user_id=1, broker_account_id=1, status=TradeState.POSITION_OPEN, instrument_token="INST1")
        p = Position(id=1, user_id=1, trade_id=1, broker_account_id=1, instrument_token="INST1", quantity=75, average_price=100.0, is_open=True)
        o = Order(id=1, trade_id=1, broker_order_id="ORD1", order_type="BUY", quantity=75, price=100.0, status="FILLED", created_at=datetime.now(timezone.utc) - timedelta(hours=1))
        s = Signal(id=1, underlying="NIFTY", strike=23500.0, option_type="CE", expiry="2026-09-17", entry_trigger=150.0, stop_loss=130.0, target=180.0, telegram_cmp=150.0)
        session.add_all([t, p, o, s])
        await session.commit()

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Reset paper state
        await client.post("/api/paper/reset")

        # Check summary metrics powering navigation badges
        sum_res = await client.get("/api/dashboard/summary")
        metrics = sum_res.json()["metrics"]
        assert metrics["active_trades"] == 0
        assert metrics["open_positions"] == 0
        assert metrics["orders_today"] == 0  # current session orders
        assert metrics["signals_today"] == 1  # historical signals preserved

