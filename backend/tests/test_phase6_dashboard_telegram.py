import os
import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from datetime import datetime, timezone
import uuid

from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy import event, text
from sqlalchemy.pool import NullPool

TEST_DB_FILE = "test_phase6.db"
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
    Base, User, BrokerAccount, TradingSettings, TelegramChannel, TelegramMessage, Signal, Trade, TradeState, Order, Position
)

db_mod.engine = test_engine
db_mod.AsyncSessionLocal = TestAsyncSessionLocal
tel_mod.AsyncSessionLocal = TestAsyncSessionLocal
dash_mod.AsyncSessionLocal = TestAsyncSessionLocal

from app.main import app
from app.database.database import get_db
from app.services.telegram_listener import telegram_listener, TelegramListenerService
from app.services.market_data_service import market_data_service
from app.brokers.kotak_neo import KotakNeoBroker
from app.config import settings

# Mock Telethon classes for isolated unit/integration tests
class MockTelethonEntity:
    def __init__(self, id, title=None, username=None, broadcast=True):
        self.id = id
        self.title = title
        self.username = username
        self.broadcast = broadcast

class MockTelethonUser:
    def __init__(self, id=987654321, first_name="Trader", last_name="User", username="user_b", phone="+919999999999"):
        self.id = id
        self.first_name = first_name
        self.last_name = last_name
        self.username = username
        self.phone = phone

class MockTelethonDialog:
    def __init__(self, id, name, is_channel=True, is_group=False, username=None, broadcast=True):
        self.id = id
        self.name = name
        self.is_channel = is_channel
        self.is_group = is_group
        self.is_user = False
        self.entity = MockTelethonEntity(id, title=name, username=username, broadcast=broadcast)

class MockTelethonClient:
    def __init__(self, authorized=True):
        self._connected = True
        self._authorized = authorized
        self._handlers = []

    def is_connected(self):
        return self._connected

    async def connect(self):
        self._connected = True

    async def disconnect(self):
        self._connected = False

    async def is_user_authorized(self):
        return self._authorized

    async def get_me(self):
        return MockTelethonUser()

    async def get_dialogs(self):
        return [
            MockTelethonDialog(id=-1001234567890, name="Dummy Broadcast Signal Channel", username="signals_channel", broadcast=True),
            MockTelethonDialog(id=-1009876543210, name="General Group Chat", is_channel=False, is_group=True, broadcast=False),
        ]

    def on(self, event_builder):
        def decorator(handler):
            self._handlers.append((event_builder, handler))
            return handler
        return decorator

    async def log_out(self):
        self._authorized = False

async def override_get_db():
    async with TestAsyncSessionLocal() as session:
        try:
            yield session
        finally:
            await session.rollback()

app.dependency_overrides[get_db] = override_get_db

@pytest_asyncio.fixture(autouse=True)
async def prepare_db():
    app.dependency_overrides[get_db] = override_get_db
    dash_mod.AsyncSessionLocal = TestAsyncSessionLocal
    db_mod.AsyncSessionLocal = TestAsyncSessionLocal
    tel_mod.AsyncSessionLocal = TestAsyncSessionLocal
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        for col, col_type in [
            ("username", "VARCHAR"),
            ("channel_type", "VARCHAR"),
            ("is_selected", "BOOLEAN DEFAULT 0")
        ]:
            try:
                await conn.execute(text(f"ALTER TABLE telegram_channels ADD COLUMN {col} {col_type}"))
            except Exception:
                pass
        try:
            await conn.execute(text("ALTER TABLE telegram_messages ADD COLUMN sender VARCHAR"))
        except Exception:
            pass
        for col, col_type in [
            ("paper_session_id", "VARCHAR"),
            ("paper_reset_at", "DATETIME")
        ]:
            try:
                await conn.execute(text(f"ALTER TABLE broker_accounts ADD COLUMN {col} {col_type}"))
            except Exception:
                pass
    
    async with TestAsyncSessionLocal() as session:
        from sqlalchemy.future import select
        existing = (await session.execute(select(User).where(User.id == 1))).scalar_one_or_none()
        if not existing:
            user = User(id=1, username="paper_trader", email="paper@trader.local", hashed_password="default_hash")
            session.add(user)
            await session.flush()
            
            broker = BrokerAccount(id=1, user_id=1, broker_name="PAPER", is_paper_trading=True)
            session.add(broker)
            
            trading_settings = TradingSettings(
                id=1,
                user_id=1,
                is_algo_active=True,
                max_daily_loss=5000.0,
                max_risk_per_trade=1000.0,
                max_trades_per_day=100,
                max_simultaneous_positions=100,
                partial_exit_percent=50.0,
                trailing_enabled=True,
                trailing_distance=5.0
            )
            session.add(trading_settings)
            await session.commit()

    yield

# =============================================================================
# 1. Telethon Client Initialization
# =============================================================================
@pytest.mark.asyncio
async def test_telethon_client_initialization():
    service = TelegramListenerService()
    mock_client = MockTelethonClient(authorized=False)
    service.set_client(mock_client)
    
    assert service.client is not None
    assert service.client.is_connected() is True

# =============================================================================
# 2. Authentication State
# =============================================================================
@pytest.mark.asyncio
async def test_telethon_authentication_state():
    service = TelegramListenerService()
    
    # Test Unauthenticated
    mock_unauth = MockTelethonClient(authorized=False)
    service.set_client(mock_unauth)
    status = await service.get_status()
    assert status["connected"] is True
    assert status["authenticated"] is False
    assert status["authenticated_user"] is None
    assert status["listener_status"] == "UNAUTHENTICATED"

    # Test Authenticated
    mock_auth = MockTelethonClient(authorized=True)
    service.set_client(mock_auth)
    status = await service.get_status()
    assert status["connected"] is True
    assert status["authenticated"] is True
    assert status["authenticated_user"]["username"] == "user_b"

# =============================================================================
# 3. Channel Discovery
# =============================================================================
@pytest.mark.asyncio
async def test_telethon_channel_discovery():
    service = TelegramListenerService()
    service.set_client(MockTelethonClient(authorized=True))
    
    channels = await service.discover_channels()
    assert len(channels) >= 2
    
    broadcast_ch = next((c for c in channels if c["channel_id"] == "-1001234567890"), None)
    assert broadcast_ch is not None
    assert broadcast_ch["channel_name"] == "Dummy Broadcast Signal Channel"
    assert broadcast_ch["channel_type"] == "broadcast"
    assert broadcast_ch["username"] == "signals_channel"

# =============================================================================
# 4. Channel Selection Persistence
# =============================================================================
@pytest.mark.asyncio
async def test_telethon_channel_selection_persistence():
    service = TelegramListenerService()
    service.set_client(MockTelethonClient(authorized=True))
    
    selected = await service.select_channel("-1001234567890", "Dummy Broadcast Signal Channel")
    assert selected["status"] == "SUCCESS"
    assert service.selected_channel_id == "-1001234567890"
    assert service.selected_channel_name == "Dummy Broadcast Signal Channel"
    
    # Verify DB persistence
    async with TestAsyncSessionLocal() as session:
        from sqlalchemy.future import select
        stmt = select(TelegramChannel).where(TelegramChannel.channel_id == "-1001234567890")
        db_ch = (await session.execute(stmt)).scalar_one()
        assert db_ch.is_selected is True

# =============================================================================
# 5. Selected-Channel Filtering
# =============================================================================
@pytest.mark.asyncio
async def test_telethon_selected_channel_filtering():
    service = TelegramListenerService()
    service.selected_channel_id = "-1001234567890"
    
    # Matching channel (both with -100 and bare ID)
    assert service.is_matching_channel("-1001234567890") is True
    assert service.is_matching_channel("1234567890") is True
    
    # Non-matching channel
    assert service.is_matching_channel("-1009999999999") is False

# =============================================================================
# 6. Message Ingestion & 8. Message Persistence
# =============================================================================
@pytest.mark.asyncio
async def test_telegram_message_ingestion_and_persistence():
    telegram_text = (
        "NIFTY 24100 CE 22 Sept 26 Expiry\n"
        "Buy above 150\n"
        "SL below 144\n"
        "Tgt above 170\n"
        "CMP 150"
    )
    msg_id = f"TEL_{uuid.uuid4().hex[:8]}"
    channel_id = "-1001234567890"

    result = await telegram_listener.process_incoming_message(
        message_id=msg_id,
        channel_id=channel_id,
        text=telegram_text,
        sender="account_a"
    )

    assert result["status"] == "SUCCESS"
    assert result["parsed"] is True
    assert result["trade_id"] is not None

    # Verify message persistence in DB
    async with TestAsyncSessionLocal() as session:
        from sqlalchemy.future import select
        stmt = select(TelegramMessage).where(TelegramMessage.telegram_message_id == msg_id)
        msg_db = (await session.execute(stmt)).scalar_one_or_none()
        assert msg_db is not None
        assert msg_db.message_text == telegram_text
        assert msg_db.sender == "account_a"
        assert msg_db.parsed_successfully is True
        assert msg_db.processing_status == "TRADE_CREATED"

# =============================================================================
# 7. Duplicate Message Protection
# =============================================================================
@pytest.mark.asyncio
async def test_duplicate_telegram_message_protection():
    telegram_text = "NIFTY 24200 CE 22 Sept 26 Expiry\nBuy above 150\nSL below 144\nTgt above 170\nCMP 150"
    msg_id = f"TEL_{uuid.uuid4().hex[:8]}"
    channel_id = "-1001234567890"

    res1 = await telegram_listener.process_incoming_message(
        message_id=msg_id,
        channel_id=channel_id,
        text=telegram_text,
        sender="account_a"
    )
    assert res1["status"] == "SUCCESS"

    # Second delivery with same (channel_id, telegram_message_id)
    res2 = await telegram_listener.process_incoming_message(
        message_id=msg_id,
        channel_id=channel_id,
        text=telegram_text,
        sender="account_a"
    )
    assert res2["status"] == "DUPLICATE"
    assert res2["parsed"] is False

# =============================================================================
# 9. Parser Integration & 11. CMP Cannot Trigger Order
# =============================================================================
@pytest.mark.asyncio
async def test_parser_integration_and_cmp_safeguard():
    # Signal where CMP is high (160) but Entry trigger is 150
    telegram_text = (
        "NIFTY 24000 CE 22 Sept 26 Expiry\n"
        "Buy above 150\n"
        "SL below 144\n"
        "Tgt above 170\n"
        "CMP 160"
    )
    msg_id = f"TEL_{uuid.uuid4().hex[:8]}"
    res = await telegram_listener.process_incoming_message(
        message_id=msg_id,
        channel_id="-1001234567890",
        text=telegram_text
    )
    assert res["status"] == "SUCCESS"
    trade_id = res["trade_id"]

    async with TestAsyncSessionLocal() as session:
        from sqlalchemy.future import select
        trade = (await session.execute(select(Trade).where(Trade.id == trade_id))).scalar_one()
        # CMP must NOT have executed an immediate market order. Trade must wait for live feed crossing!
        assert trade.status == TradeState.WAITING_FOR_ENTRY
        assert trade.entry_price is None

# =============================================================================
# 10. Restart/Reconnect Behavior
# =============================================================================
@pytest.mark.asyncio
async def test_restart_recovery_behavior():
    # Save a selected channel in DB
    test_ch_id = f"-100{uuid.uuid4().int % 1000000000:09d}"
    async with TestAsyncSessionLocal() as session:
        from sqlalchemy.future import select
        ch = TelegramChannel(
            channel_id=test_ch_id,
            channel_name="Persisted Signal Broadcast",
            is_selected=True,
            is_active=True
        )
        session.add(ch)
        await session.commit()

    service = TelegramListenerService()
    assert service.selected_channel_id is None
    
    # Simulate restart restore
    await service.restore_selected_channel()
    assert service.selected_channel_id == test_ch_id
    assert service.selected_channel_name == "Persisted Signal Broadcast"

# =============================================================================
# 12. Live Orders Remain Disabled (Safety Hard-Lock)
# =============================================================================
@pytest.mark.asyncio
async def test_safety_check_live_execution_permanently_disabled():
    broker = KotakNeoBroker()
    with pytest.raises(NotImplementedError):
        await broker.place_order({"instrument": "test", "quantity": 1})
    with pytest.raises(NotImplementedError):
        await broker.modify_order("ord_123", {"price": 100})
    with pytest.raises(NotImplementedError):
        await broker.cancel_order("ord_123")
    with pytest.raises(NotImplementedError):
        await broker.exit_position("pos_123")

# =============================================================================
# Dashboard APIs & Endpoints Verification
# =============================================================================
@pytest.mark.asyncio
async def test_dashboard_apis_and_channels_routes():
    telegram_listener.set_client(MockTelethonClient(authorized=True))
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        # Status
        r_st = await ac.get("/api/telegram/status")
        assert r_st.status_code == 200
        data_st = r_st.json()
        assert data_st["connected"] is True
        assert "api_hash" not in r_st.text  # Security check: Never leak secrets!

        # Channels discovery
        r_ch = await ac.get("/api/telegram/channels")
        assert r_ch.status_code == 200
        chs = r_ch.json()
        assert len(chs) >= 1

        # Channel selection
        r_sel = await ac.post("/api/telegram/channels/select", json={
            "channel_id": "-1001234567890",
            "channel_name": "Dummy Broadcast Signal Channel"
        })
        assert r_sel.status_code == 200
        assert r_sel.json()["status"] == "SUCCESS"

        # Summary
        r_sum = await ac.get("/api/dashboard/summary")
        assert r_sum.status_code == 200
        assert r_sum.json()["mode"] == "PAPER"
        assert r_sum.json()["live_orders"] == "DISABLED"
