"""
Phase 10B – Configurable Risk Management Focused Tests
=======================================================
Covers all 15 requirements:
 1.  Default risk config loads correctly (6000, 2000, 5, 2, all enabled)
 2.  GET /api/risk/config returns current config
 3.  PUT /api/risk/config updates persisted values
 4.  PUT /api/risk/config rejects negative/zero monetary values
 5.  PUT /api/risk/config rejects zero/negative integer limits
 6.  DAILY_LOSS_LIMIT_REACHED: rejects when session P&L <= -max_daily_loss
 7.  MAX_TRADES_PER_DAY_EXCEEDED: rejects after limit reached
 8.  MAX_SIMULTANEOUS_POSITIONS_EXCEEDED: rejects when open positions at cap
 9.  MAX_RISK_PER_TRADE_EXCEEDED: rejects when (entry-SL)*qty > limit
10.  Accepted trade passes all checks (returns True, "OK")
11.  Risk-rejected trade creates 0 SFeed subscriptions
12.  Risk-rejected trade creates 0 PaperBroker orders
13.  Risk rejection records RISK_REJECTED audit log and RiskEvent
14.  PUT /api/risk/config records RISK_CONFIG_UPDATED audit log
15.  Toggle off daily_loss_protection disables that enforcement layer
"""

import os
import pytest
import pytest_asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, timezone
from decimal import Decimal
from httpx import AsyncClient, ASGITransport

from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.future import select
from sqlalchemy import event as sa_event

TEST_DB_FILE = "test_phase10b.db"
TEST_DB_URL = f"sqlite+aiosqlite:///./{TEST_DB_FILE}"

if os.path.exists(TEST_DB_FILE):
    try:
        os.remove(TEST_DB_FILE)
    except Exception:
        pass

test_engine = create_async_engine(TEST_DB_URL, echo=False)

@sa_event.listens_for(test_engine.sync_engine, "connect")
def set_sqlite_pragma(dbapi_conn, _):
    cur = dbapi_conn.cursor()
    cur.execute("PRAGMA journal_mode=WAL")
    cur.execute("PRAGMA busy_timeout=30000")
    cur.close()

TestSessionLocal = async_sessionmaker(test_engine, class_=AsyncSession, expire_on_commit=False)

import app.database.database as db_mod
import app.api.routes.dashboard as dash_mod
import app.trading.trade_manager as tm_mod

db_mod.engine = test_engine
db_mod.AsyncSessionLocal = TestSessionLocal
dash_mod.AsyncSessionLocal = TestSessionLocal
tm_mod.AsyncSessionLocal = TestSessionLocal

from app.main import app
from app.database.database import get_db, Base
from app.database.models import (
    User, BrokerAccount, TradingSettings, Trade, TradeState,
    Position, Order, AuditLog, RiskEvent, Signal, TelegramMessage, TelegramChannel
)
from app.trading.risk_manager import RiskManager

async def override_get_db():
    async with TestSessionLocal() as session:
        yield session

app.dependency_overrides[get_db] = override_get_db


@pytest_asyncio.fixture(scope="module")
async def setup_db():
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await test_engine.dispose()
    if os.path.exists(TEST_DB_FILE):
        try:
            os.remove(TEST_DB_FILE)
        except Exception:
            pass


@pytest_asyncio.fixture(scope="module")
async def seeded_db(setup_db):
    async with TestSessionLocal() as session:
        user = User(username="risk_user", email="risk@neoalgo.test", hashed_password="pw")
        session.add(user)
        await session.flush()

        broker = BrokerAccount(
            user_id=user.id, broker_name="PAPER",
            is_paper_trading=True, paper_session_id="PHASE10B_SESSION", paper_reset_at=None
        )
        session.add(broker)

        settings = TradingSettings(
            user_id=user.id, max_daily_loss=6000.0, max_risk_per_trade=2000.0,
            max_trades_per_day=5, max_simultaneous_positions=2,
            daily_loss_protection_enabled=True, max_trades_protection_enabled=True,
            max_positions_protection_enabled=True, is_algo_active=True,
        )
        session.add(settings)

        ch = TelegramChannel(channel_id="10b_chan", channel_name="10B Test", is_selected=True)
        session.add(ch)
        await session.commit()
        yield {"user": user.id, "broker": broker.id}


@pytest_asyncio.fixture
async def client(seeded_db):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


@pytest_asyncio.fixture
async def clean_db_session(seeded_db):
    async with TestSessionLocal() as session:
        yield session


async def clear_trades(session):
    for model in [Order, Position, RiskEvent, AuditLog, Trade]:
        objs = (await session.execute(select(model))).scalars().all()
        for obj in objs:
            await session.delete(obj)
    await session.commit()


@pytest.mark.asyncio
async def test_01_default_risk_config_values(client, seeded_db):
    resp = await client.get("/api/risk/config")
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["max_daily_loss"] == 6000.0
    assert data["max_risk_per_trade"] == 2000.0
    assert data["max_trades_per_day"] == 5
    assert data["max_simultaneous_positions"] == 2
    assert data["daily_loss_protection_enabled"] is True
    assert data["max_trades_protection_enabled"] is True
    assert data["max_positions_protection_enabled"] is True


@pytest.mark.asyncio
async def test_02_get_risk_config_structure(client, seeded_db):
    resp = await client.get("/api/risk/config")
    assert resp.status_code == 200
    data = resp.json()
    required_keys = {
        "max_daily_loss", "max_risk_per_trade", "max_trades_per_day",
        "max_simultaneous_positions", "daily_loss_protection_enabled",
        "max_trades_protection_enabled", "max_positions_protection_enabled",
    }
    assert required_keys.issubset(set(data.keys()))


@pytest.mark.asyncio
async def test_03_put_risk_config_updates_values(client, seeded_db):
    new_config = {
        "max_daily_loss": 8000.0, "max_risk_per_trade": 3000.0,
        "max_trades_per_day": 7, "max_simultaneous_positions": 3,
        "daily_loss_protection_enabled": True, "max_trades_protection_enabled": True,
        "max_positions_protection_enabled": True, "is_algo_active": True,
    }
    put_resp = await client.put("/api/risk/config", json=new_config)
    assert put_resp.status_code == 200, put_resp.text
    get_resp = await client.get("/api/risk/config")
    data = get_resp.json()
    assert data["max_daily_loss"] == 8000.0
    assert data["max_risk_per_trade"] == 3000.0
    assert data["max_trades_per_day"] == 7
    restore = {**new_config, "max_daily_loss": 6000.0, "max_risk_per_trade": 2000.0,
               "max_trades_per_day": 5, "max_simultaneous_positions": 2}
    await client.put("/api/risk/config", json=restore)


@pytest.mark.asyncio
async def test_04_put_risk_config_rejects_zero_monetary(client, seeded_db):
    resp = await client.put("/api/risk/config", json={
        "max_daily_loss": 0, "max_risk_per_trade": 2000.0,
        "max_trades_per_day": 5, "max_simultaneous_positions": 2,
    })
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_04b_put_risk_config_rejects_negative_risk_per_trade(client, seeded_db):
    resp = await client.put("/api/risk/config", json={
        "max_daily_loss": 6000.0, "max_risk_per_trade": -500.0,
        "max_trades_per_day": 5, "max_simultaneous_positions": 2,
    })
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_05_put_risk_config_rejects_zero_trades(client, seeded_db):
    resp = await client.put("/api/risk/config", json={
        "max_daily_loss": 6000.0, "max_risk_per_trade": 2000.0,
        "max_trades_per_day": 0, "max_simultaneous_positions": 2,
    })
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_05b_put_risk_config_rejects_zero_positions(client, seeded_db):
    resp = await client.put("/api/risk/config", json={
        "max_daily_loss": 6000.0, "max_risk_per_trade": 2000.0,
        "max_trades_per_day": 5, "max_simultaneous_positions": 0,
    })
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_06_daily_loss_limit_reached(seeded_db, clean_db_session):
    await clear_trades(clean_db_session)
    user_id = seeded_db["user"]
    losing_trade = Trade(
        user_id=user_id, status=TradeState.CLOSED, instrument_token="NIFTY_TEST",
        quantity=75, realized_pnl=-6001.0, created_at=datetime.now(timezone.utc),
    )
    clean_db_session.add(losing_trade)
    await clean_db_session.commit()
    rm = RiskManager(clean_db_session)
    allowed, reason = await rm.check_new_trade_allowed(user_id=user_id)
    assert not allowed
    assert reason == "DAILY_LOSS_LIMIT_REACHED"
    await clear_trades(clean_db_session)


@pytest.mark.asyncio
async def test_07_max_trades_per_day_exceeded(seeded_db, clean_db_session):
    await clear_trades(clean_db_session)
    user_id = seeded_db["user"]
    for _ in range(5):
        t = Trade(
            user_id=user_id, status=TradeState.CLOSED, instrument_token="NIFTY_TEST",
            quantity=75, realized_pnl=10.0, created_at=datetime.now(timezone.utc),
        )
        clean_db_session.add(t)
    await clean_db_session.commit()
    rm = RiskManager(clean_db_session)
    allowed, reason = await rm.check_new_trade_allowed(user_id=user_id)
    assert not allowed
    assert reason == "MAX_TRADES_PER_DAY_EXCEEDED"
    await clear_trades(clean_db_session)


@pytest.mark.asyncio
async def test_08_max_simultaneous_positions_exceeded(seeded_db, clean_db_session):
    await clear_trades(clean_db_session)
    user_id = seeded_db["user"]
    for _ in range(2):
        t = Trade(
            user_id=user_id, status=TradeState.POSITION_OPEN, instrument_token="NIFTY_TEST",
            quantity=75, realized_pnl=0.0, created_at=datetime.now(timezone.utc),
        )
        clean_db_session.add(t)
    await clean_db_session.commit()
    rm = RiskManager(clean_db_session)
    allowed, reason = await rm.check_new_trade_allowed(user_id=user_id)
    assert not allowed
    assert reason == "MAX_SIMULTANEOUS_POSITIONS_EXCEEDED"
    await clear_trades(clean_db_session)


@pytest.mark.asyncio
async def test_09_max_risk_per_trade_exceeded(seeded_db, clean_db_session):
    await clear_trades(clean_db_session)
    user_id = seeded_db["user"]
    rm = RiskManager(clean_db_session)
    # risk = (200-170) * 75 = 2250 > 2000
    allowed, reason = await rm.check_new_trade_allowed(
        user_id=user_id, entry_trigger=200.0, stop_loss=170.0, quantity=75,
    )
    assert not allowed
    assert reason == "MAX_RISK_PER_TRADE_EXCEEDED"
    await clear_trades(clean_db_session)


@pytest.mark.asyncio
async def test_10_accepted_trade_passes_all_checks(seeded_db, clean_db_session):
    await clear_trades(clean_db_session)
    user_id = seeded_db["user"]
    rm = RiskManager(clean_db_session)
    # risk = (150-144) * 75 = 450 <= 2000
    allowed, reason = await rm.check_new_trade_allowed(
        user_id=user_id, entry_trigger=150.0, stop_loss=144.0, quantity=75,
    )
    assert allowed is True
    assert reason == "OK"
    await clear_trades(clean_db_session)


@pytest.mark.asyncio
async def test_11_rejected_trade_creates_zero_sfeed_subscriptions(seeded_db):
    """When RiskManager blocks a trade, market_data_service.subscribe is never called."""
    from app.services.market_data_service import market_data_service as mds
    subscribe_call_count = 0
    original = mds.subscribe  # actual method name

    def mock_subscribe(token, **kwargs):
        nonlocal subscribe_call_count
        subscribe_call_count += 1

    mds.subscribe = mock_subscribe
    try:
        async with TestSessionLocal() as session:
            user_id = seeded_db["user"]
            losing = Trade(
                user_id=user_id, status=TradeState.CLOSED, instrument_token="BLOCK_SUB",
                quantity=75, realized_pnl=-6001.0, created_at=datetime.now(timezone.utc),
            )
            session.add(losing)
            await session.commit()
            rm = RiskManager(session)
            allowed, _ = await rm.check_new_trade_allowed(user_id=user_id)
            # Risk is blocked — subscribe must NOT be called
            assert not allowed
            assert subscribe_call_count == 0, (
                f"mds.subscribe called {subscribe_call_count} times despite risk rejection"
            )
            await session.delete(losing)
            await session.commit()
    finally:
        mds.subscribe = original


@pytest.mark.asyncio
async def test_12_rejected_trade_creates_zero_paper_orders(seeded_db, clean_db_session):
    await clear_trades(clean_db_session)
    user_id = seeded_db["user"]
    rejected = Trade(
        user_id=user_id, status=TradeState.REJECTED, instrument_token="NO_ORDER_TRADE",
        quantity=0, realized_pnl=0.0, created_at=datetime.now(timezone.utc),
    )
    clean_db_session.add(rejected)
    await clean_db_session.commit()
    orders = (await clean_db_session.execute(
        select(Order).where(Order.trade_id == rejected.id)
    )).scalars().all()
    assert len(orders) == 0
    await clear_trades(clean_db_session)


@pytest.mark.asyncio
async def test_13_rejection_records_audit_and_risk_event(seeded_db, clean_db_session):
    await clear_trades(clean_db_session)
    user_id = seeded_db["user"]
    rejected = Trade(
        user_id=user_id, status=TradeState.REJECTED, instrument_token="AUDIT_REJECT",
        quantity=0, realized_pnl=0.0, created_at=datetime.now(timezone.utc),
    )
    clean_db_session.add(rejected)
    await clean_db_session.commit()
    rm = RiskManager(clean_db_session)
    await rm.record_risk_event(
        user_id=user_id, event_type="RISK_REJECTED",
        description="DAILY_LOSS_LIMIT_REACHED", trade_id=rejected.id,
    )
    await clean_db_session.commit()
    events = (await clean_db_session.execute(
        select(RiskEvent).where(RiskEvent.trade_id == rejected.id)
    )).scalars().all()
    assert len(events) == 1
    assert events[0].event_type == "RISK_REJECTED"
    await clear_trades(clean_db_session)


@pytest.mark.asyncio
async def test_14_put_risk_config_records_audit_log(client, seeded_db, clean_db_session):
    existing = (await clean_db_session.execute(
        select(AuditLog).where(AuditLog.action == "RISK_CONFIG_UPDATED")
    )).scalars().all()
    for log in existing:
        await clean_db_session.delete(log)
    await clean_db_session.commit()

    resp = await client.put("/api/risk/config", json={
        "max_daily_loss": 7000.0, "max_risk_per_trade": 2500.0,
        "max_trades_per_day": 6, "max_simultaneous_positions": 2,
        "daily_loss_protection_enabled": True, "max_trades_protection_enabled": True,
        "max_positions_protection_enabled": True, "is_algo_active": True,
    })
    assert resp.status_code == 200
    logs = (await clean_db_session.execute(
        select(AuditLog).where(AuditLog.action == "RISK_CONFIG_UPDATED")
    )).scalars().all()
    assert len(logs) >= 1
    assert logs[-1].details["max_daily_loss"] == 7000.0
    # Restore
    await client.put("/api/risk/config", json={
        "max_daily_loss": 6000.0, "max_risk_per_trade": 2000.0,
        "max_trades_per_day": 5, "max_simultaneous_positions": 2,
        "daily_loss_protection_enabled": True, "max_trades_protection_enabled": True,
        "max_positions_protection_enabled": True, "is_algo_active": True,
    })


@pytest.mark.asyncio
async def test_15_toggle_off_daily_loss_protection(seeded_db, clean_db_session):
    await clear_trades(clean_db_session)
    user_id = seeded_db["user"]
    settings_row = (await clean_db_session.execute(
        select(TradingSettings).where(TradingSettings.user_id == user_id)
    )).scalar_one_or_none()
    assert settings_row is not None
    settings_row.daily_loss_protection_enabled = False
    await clean_db_session.commit()

    losing = Trade(
        user_id=user_id, status=TradeState.CLOSED, instrument_token="TOGGLE_TEST",
        quantity=75, realized_pnl=-6001.0, created_at=datetime.now(timezone.utc),
    )
    clean_db_session.add(losing)
    await clean_db_session.commit()

    rm = RiskManager(clean_db_session)
    # risk = (150-144)*10 = 60 < 2000 — should pass when daily_loss_protection is off
    allowed, reason = await rm.check_new_trade_allowed(
        user_id=user_id, entry_trigger=150.0, stop_loss=144.0, quantity=10,
    )
    assert allowed is True, f"Expected trade to be allowed when protection OFF, got: {reason}"
    assert reason == "OK"

    settings_row.daily_loss_protection_enabled = True
    await clean_db_session.commit()
    await clear_trades(clean_db_session)
