import os
import time
import pytest
import pytest_asyncio
from unittest.mock import AsyncMock, patch, MagicMock
from httpx import AsyncClient, ASGITransport
from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy import event, text
from sqlalchemy.pool import NullPool

TEST_DB_FILE = "test_phase10a.db"
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
import app.api.routes.dashboard as dash_mod
import app.trading.trade_manager as tm_mod
from app.database.models import (
    Base, User, BrokerAccount, TradingSettings, Signal,
    Trade, TradeState, Order, Position
)

db_mod.engine = test_engine
db_mod.AsyncSessionLocal = TestAsyncSessionLocal
dash_mod.AsyncSessionLocal = TestAsyncSessionLocal
tm_mod.AsyncSessionLocal = TestAsyncSessionLocal

from app.main import app
from app.database.database import get_db
from app.services.market_data_service import market_data_service
from app.trading.trade_manager import TradeManager
from app.brokers.kotak_neo import KotakNeoBroker

async def override_get_db():
    async with TestAsyncSessionLocal() as session:
        yield session

app.dependency_overrides[get_db] = override_get_db


@pytest_asyncio.fixture(autouse=True)
async def prepare_database():
    dash_mod.AsyncSessionLocal = TestAsyncSessionLocal
    db_mod.AsyncSessionLocal = TestAsyncSessionLocal
    tm_mod.AsyncSessionLocal = TestAsyncSessionLocal

    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)

    async with TestAsyncSessionLocal() as session:
        user = User(id=1, username="paper_trader", email="paper@trader.local", hashed_password="default_hash")
        session.add(user)
        await session.flush()

        broker = BrokerAccount(id=1, user_id=1, broker_name="PAPER", is_paper_trading=True)
        session.add(broker)

        trading_settings = TradingSettings(id=1, user_id=1, is_algo_active=True)
        session.add(trading_settings)
        await session.commit()
    dash_mod._profile_cache = {"data": None, "timestamp": 0.0}
    dash_mod._scrip_count_cache = {"scrip_count": 0, "nifty_count": 0, "cache_id": None}
    yield
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest.mark.asyncio
async def test_broker_status_profile_caching():
    """Verify that /api/broker/status caches profile responses for 5 minutes."""
    mock_profile = {"client_code": "TEST_UCC"}

    with patch.object(dash_mod.kotak_broker, "get_profile", new_callable=AsyncMock) as mock_get_prof, \
         patch.object(dash_mod.kotak_broker, "auth_status", "CONNECTED"):
        mock_get_prof.return_value = mock_profile

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            # First call: cache miss, invokes get_profile()
            res1 = await client.get("/api/broker/status")
            assert res1.status_code == 200
            assert mock_get_prof.call_count == 1
            data1 = res1.json()
            assert data1["profile"]["client_code"] == "TEST_UCC"

            # Second call immediately: cache hit, must NOT invoke get_profile() again
            res2 = await client.get("/api/broker/status")
            assert res2.status_code == 200
            assert mock_get_prof.call_count == 1  # Unchanged!

            # Fast-forward cache timestamp by 301 seconds (past 300s TTL)
            dash_mod._profile_cache["timestamp"] -= 301.0

            # Third call: expired cache, invokes get_profile() again
            res3 = await client.get("/api/broker/status")
            assert res3.status_code == 200
            assert mock_get_prof.call_count == 2


@pytest.mark.asyncio
async def test_broker_status_scrip_count_caching():
    """Verify scrip counts are cached and not re-iterated on every request."""
    mock_scrips = [
        {"pSymbol": "NIFTY26SEP24000CE", "pSymbolName": "NIFTY", "pInstType": "OPTIDX"},
        {"pSymbol": "BANKNIFTY26SEP50000CE", "pSymbolName": "BANKNIFTY", "pInstType": "OPTIDX"},
        {"pSymbol": "RELIANCE", "pSymbolName": "RELIANCE", "pInstType": "EQUITY"},
    ]

    mock_resolver = MagicMock()
    mock_resolver._cache = mock_scrips

    with patch.object(dash_mod.telegram_listener, "resolver", mock_resolver), \
         patch.object(dash_mod.kotak_broker, "auth_status", "DISCONNECTED"):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            res1 = await client.get("/api/broker/status")
            assert res1.status_code == 200
            data1 = res1.json()
            assert data1["instrument_count"] == 3
            assert data1["active_nifty_contracts"] == 1
            assert dash_mod._scrip_count_cache["cache_id"] == 3

            # Second call: cache reused
            res2 = await client.get("/api/broker/status")
            assert res2.status_code == 200
            data2 = res2.json()
            assert data2["instrument_count"] == 3
            assert data2["active_nifty_contracts"] == 1


@pytest.mark.asyncio
async def test_dashboard_summary_aggregation():
    """Verify consolidated SQL aggregation accurately sums trades, orders, and signals."""
    now = datetime.now(timezone.utc)
    async with TestAsyncSessionLocal() as session:
        # 1. Signals
        sig1 = Signal(
            message_id=None, underlying="NIFTY", strike=23500.0,
            option_type="CE", expiry="2026-09-22", entry_trigger=150.0,
            stop_loss=140.0, target=170.0, created_at=now
        )
        sig2 = Signal(
            message_id=None, underlying="NIFTY", strike=23600.0,
            option_type="CE", expiry="2026-09-22", entry_trigger=160.0,
            stop_loss=150.0, target=180.0, created_at=now
        )
        session.add_all([sig1, sig2])
        await session.commit()
        await session.refresh(sig1)

        # 2. Trades: 1 position_open, 1 waiting for entry, 1 closed
        t1 = Trade(
            user_id=1, broker_account_id=1, signal_id=sig1.id,
            instrument_token="56980", status=TradeState.POSITION_OPEN,
            quantity=50, entry_price=150.0, realized_pnl=250.0,
            created_at=now, updated_at=now
        )
        t2 = Trade(
            user_id=1, broker_account_id=1, signal_id=sig1.id,
            instrument_token="56984", status=TradeState.WAITING_FOR_ENTRY,
            quantity=50, entry_price=0.0, realized_pnl=0.0,
            created_at=now, updated_at=now
        )
        t3 = Trade(
            user_id=1, broker_account_id=1, signal_id=sig1.id,
            instrument_token="56980", status=TradeState.CLOSED,
            quantity=50, entry_price=150.0, exit_price=160.0, realized_pnl=500.0,
            created_at=now, updated_at=now
        )
        session.add_all([t1, t2, t3])
        await session.commit()
        await session.refresh(t1)

        # 3. Open Position
        p1 = Position(
            user_id=1, trade_id=t1.id, broker_account_id=1,
            instrument_token="56980", quantity=50, average_price=150.0, is_open=True,
            created_at=now
        )
        session.add(p1)

        # 4. Orders: 2 orders
        o1 = Order(
            trade_id=t1.id, broker_order_id="ORD_1", order_type="BUY",
            quantity=50, price=150.0, status="FILLED", created_at=now
        )
        o2 = Order(
            trade_id=t2.id, broker_order_id="ORD_2", order_type="BUY",
            quantity=50, price=150.0, status="PENDING", created_at=now
        )
        session.add_all([o1, o2])
        await session.commit()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        res = await client.get("/api/dashboard/summary")
        assert res.status_code == 200
        summary = res.json()
        metrics = summary["metrics"]

        # Check aggregated metrics
        assert metrics["active_trades"] == 2  # POSITION_OPEN and WAITING_FOR_ENTRY
        assert metrics["open_positions"] == 1
        assert metrics["today_pnl"] == 750.0  # 250 + 500
        assert metrics["signals_today"] == 2
        assert metrics["orders_today"] == 2


@pytest.mark.asyncio
async def test_trade_manager_evaluate_market_prices_joined_query():
    """Verify evaluate_market_prices executes single joined query for trade + signal."""
    async with TestAsyncSessionLocal() as session:
        sig = Signal(
            message_id=None, underlying="NIFTY", strike=23500.0,
            option_type="CE", expiry="2026-09-22", entry_trigger=150.0,
            stop_loss=140.0, target=170.0
        )
        session.add(sig)
        await session.commit()
        await session.refresh(sig)

        trd = Trade(
            user_id=1, broker_account_id=1, signal_id=sig.id,
            instrument_token="TOKEN_JOIN_TEST",
            status=TradeState.WAITING_FOR_ENTRY, quantity=50,
            entry_price=0.0, realized_pnl=0.0
        )
        session.add(trd)
        await session.commit()
        await session.refresh(trd)

        tm = TradeManager(session, MagicMock())
        with patch("app.services.market_data_service.market_data_service") as mock_mds:
            mock_mds.is_stale.return_value = False

            # Evaluate at price 145 (below trigger 150) -> should remain WAITING_FOR_ENTRY
            await tm.evaluate_market_prices("TOKEN_JOIN_TEST", 145.0)

            refreshed = await session.get(Trade, trd.id)
            assert refreshed.status == TradeState.WAITING_FOR_ENTRY

            # Evaluate at price 152 (above trigger 150) -> triggers entry
            with patch.object(tm, "_place_paper_order", new_callable=AsyncMock) as mock_order, \
                 patch.object(tm, "_update_position", new_callable=AsyncMock) as mock_pos:
                await tm.evaluate_market_prices("TOKEN_JOIN_TEST", 152.0)
                assert mock_order.called
                assert mock_pos.called

                refreshed_after = await session.get(Trade, trd.id)
                assert refreshed_after.status == TradeState.POSITION_OPEN


@pytest.mark.asyncio
async def test_active_trades_ltp_enrichment():
    """Verify active trades fetch enriches latest LTP directly from MarketDataService."""
    async with TestAsyncSessionLocal() as session:
        trd = Trade(
            user_id=1, broker_account_id=1, signal_id=None,
            instrument_token="56980", status=TradeState.POSITION_OPEN,
            quantity=50, entry_price=175.0, realized_pnl=0.0
        )
        session.add(trd)
        await session.commit()

    market_data_service.subscribe("56980", initial_ltp=182.50)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        res = await client.get("/api/trades?scope=active")
        assert res.status_code == 200
        trades = res.json()
        assert len(trades) >= 1
        matching = next(t for t in trades if t["instrument"] == "56980")
        assert matching["current_ltp"] == 182.50
