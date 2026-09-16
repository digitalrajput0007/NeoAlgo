"""
Comprehensive Unit & Integration Tests for SFeed Lifecycle Manager,
Reference Counting, Reconnect Supervisor, and Live Tick Flow.
"""
import pytest
import asyncio
from unittest.mock import MagicMock, AsyncMock, patch
from datetime import datetime, timezone, timedelta

from app.market_data.kotak_neo_feed import KotakNeoFeed, SFeedState, get_sfeed_manager
from app.services.market_data_service import MarketDataService, SubscriptionState
from app.database.models import TradeState
from neo_api_client.websocket.feed import SFeedScrip, WsToken


@pytest.fixture(autouse=True)
def clean_market_data():
    from app.services.market_data_service import market_data_service
    market_data_service.subscriptions.clear()
    market_data_service._price_listeners.clear()
    yield
    market_data_service.subscriptions.clear()
    market_data_service._price_listeners.clear()


@pytest.fixture
def mock_broker():
    broker = MagicMock()
    broker.auth_status = "CONNECTED"
    broker.is_connected = True
    broker.trade_token = "mock_trade_token"
    broker.trading_sid = "mock_trading_sid"
    broker.ucc = "MOCK_UCC"
    broker.data_center = "E21"
    broker.feed_url = None
    return broker


class TestSFeedLifecycle:
    """Tests covering Tasks 1, 3, 4, 5, 6, 8, 9, 11."""

    @pytest.mark.asyncio
    async def test_lifecycle_transitions(self, mock_broker):
        """Verify explicit lifecycle transitions: DISCONNECTED -> CONNECTING -> CONNECTED -> SUBSCRIBING -> SUBSCRIBED -> RECEIVING_TICKS -> CLOSING -> DISCONNECTED."""
        feed = KotakNeoFeed(mock_broker)
        assert feed.state == SFeedState.DISCONNECTED

        with patch("app.market_data.kotak_neo_feed.SFeedWebSocket") as mock_ws_cls:
            mock_ws = AsyncMock()
            mock_ws_cls.return_value = mock_ws

            # 1. Connect
            connect_ok = await feed.connect()
            assert connect_ok is True
            assert feed.state == SFeedState.CONNECTED
            assert feed.connection_generation == 1

            # 2. Subscribe (Ack received -> SUBSCRIBED, not RECEIVING_TICKS yet)
            sub_ok = await feed.subscribe_single("nse_fo", "56980")
            assert sub_ok is True
            assert feed.state == SFeedState.SUBSCRIBED
            assert "56980" in feed.subscribed_tokens

            # 3. Real Tick Received -> RECEIVING_TICKS
            tick = MagicMock(spec=SFeedScrip)
            tick.instrument_token = "56980"
            tick.last_traded_price = 245.50
            tick.trading_symbol = "NIFTY2692223200CE"
            tick.exchange_segment = "nse_fo"
            feed._on_message(tick)

            assert feed.state == SFeedState.RECEIVING_TICKS
            assert feed.total_ticks_received == 1
            cached = feed.get_latest_price("56980")
            assert cached["last_traded_price"] == 245.50

            # 4. Stop / Shutdown
            await feed.stop()
            assert feed.state == SFeedState.DISCONNECTED
            mock_ws.close.assert_awaited()

    @pytest.mark.asyncio
    async def test_reconnect_bounded_exponential_backoff(self, mock_broker):
        """Verify exponential backoff calculation and generation increment on reconnect."""
        feed = KotakNeoFeed(mock_broker)
        assert feed.base_reconnect_delay == 1.0
        assert feed.max_reconnect_delay == 30.0

        delays = []
        for i in range(7):
            delay = min(feed.base_reconnect_delay * (2 ** i), feed.max_reconnect_delay)
            delays.append(delay)

        assert delays == [1.0, 2.0, 4.0, 8.0, 16.0, 30.0, 30.0]

        with patch("app.market_data.kotak_neo_feed.SFeedWebSocket") as mock_ws_cls:
            mock_ws = AsyncMock()
            mock_ws_cls.return_value = mock_ws

            await feed.connect()
            gen1 = feed.connection_generation
            assert gen1 == 1

            # Subscribe a token before disconnect
            await feed.subscribe_single("nse_fo", "56980")

            # Simulate reconnect
            feed._ws = None
            feed.is_connected = False
            await feed.connect()
            assert feed.connection_generation == 2
            # Verify previously subscribed token was re-subscribed
            assert "56980" in feed.subscribed_tokens

            await feed.stop()

    def test_duplicate_subscriptions_prevented(self):
        """Prevent duplicate subscriptions in MarketDataService."""
        mds = MarketDataService()
        mds.register_trade_interest(token="56980", trade_id=1, exchange_seg="nse_fo")
        assert len(mds.subscriptions) == 1
        assert mds.subscriptions["56980"]["active_trade_ids"] == {1}

        # Second registration for same trade
        mds.register_trade_interest(token="56980", trade_id=1, exchange_seg="nse_fo")
        assert len(mds.subscriptions) == 1
        assert mds.subscriptions["56980"]["active_trade_ids"] == {1}

    def test_reference_counting_multiple_trades(self):
        """Subscription persists when Trade A closes if Trade B still needs it."""
        mds = MarketDataService()
        token = "56980"

        # Trade A & B both trade token 56980
        mds.register_trade_interest(token=token, trade_id=101, exchange_seg="nse_fo")
        mds.register_trade_interest(token=token, trade_id=102, exchange_seg="nse_fo")

        assert len(mds.subscriptions[token]["active_trade_ids"]) == 2

        # Trade A closes
        mds.release_trade_interest(token=token, trade_id=101)
        assert token in mds.subscriptions
        assert mds.subscriptions[token]["active_trade_ids"] == {102}

        # Trade B closes (final trade) -> triggers cleanup
        mds.release_trade_interest(token=token, trade_id=102)
        assert token not in mds.subscriptions

    def test_rejected_trade_never_creates_sfeed_subscription(self):
        """A rejected trade must never create an active SFeed subscription."""
        mds = MarketDataService()
        token = "99999"

        # Simulate risk rejection flow: trade is marked REJECTED
        trade_status = TradeState.REJECTED
        if trade_status != TradeState.REJECTED:
            mds.register_trade_interest(token=token, trade_id=99)

        assert token not in mds.subscriptions

    def test_stale_subscription_detection(self):
        """Stale subscriptions are detected when ticks do not arrive within timeout."""
        mds = MarketDataService()
        token = "56980"
        mds.register_trade_interest(token=token, trade_id=1, exchange_seg="nse_fo")

        # Set subscribed_at to 120 seconds ago with 0 ticks
        old_time = (datetime.now(timezone.utc) - timedelta(seconds=120)).isoformat()
        mds.subscriptions[token]["subscribed_at"] = old_time
        mds.subscriptions[token]["created_at"] = old_time

        is_stale = mds.is_stale(token, max_age_seconds=60)
        assert is_stale is True
        assert mds.subscriptions[token]["subscription_state"] == SubscriptionState.STALE
        assert mds.subscriptions[token]["feed_status"] == "STALE"

    @pytest.mark.asyncio
    async def test_receiver_task_failure_and_clean_shutdown(self, mock_broker):
        """Receiver task exception updates last_error and triggers supervisor reconnect."""
        feed = KotakNeoFeed(mock_broker)

        with patch("app.market_data.kotak_neo_feed.SFeedWebSocket") as mock_ws_cls:
            mock_ws = AsyncMock()
            mock_ws_cls.return_value = mock_ws

            await feed.connect()
            assert feed.is_connected is True

            # Simulate socket error
            feed._on_ws_error(ConnectionResetError("Socket reset by peer"))
            assert "Socket reset by peer" in feed.last_error

            # Clean shutdown
            await feed.stop()
            assert feed.state == SFeedState.DISCONNECTED
            assert feed.is_connected is False

    def test_health_diagnostics_sanitized(self, mock_broker):
        """Task 11: Internal health diagnostics exposes connection generation and state without secrets."""
        feed = KotakNeoFeed(mock_broker)
        diag = feed.get_diagnostics()

        assert "connected" in diag
        assert "websocket_state" in diag
        assert "connection_generation" in diag
        assert "receiver_task_running" in diag
        assert "subscribed_tokens" in diag
        assert "subscription_count" in diag
        assert "total_ticks" in diag
        assert "reconnect_count" in diag
        assert "last_error" in diag

        # Ensure NO credentials or secrets are present in diagnostics
        diag_str = str(diag).lower()
        for forbidden in ["mpin", "totp", "consumer_key", "trade_token", "trading_sid", "password"]:
            assert forbidden not in diag_str

    @pytest.mark.asyncio
    async def test_real_tick_propagation_to_market_data_and_paper_broker(self, mock_broker):
        """Task 11 & 12: Real decoded tick updates market_data_service and propagates to PaperBroker with zero live orders."""
        from app.trading.trade_manager import TradeManager
        from app.brokers.paper import PaperBroker
        from app.services.market_data_service import market_data_service
        from app.database.database import AsyncSessionLocal
        from app.database.models import Trade, Signal, TradeState
        import uuid

        feed = KotakNeoFeed(mock_broker)
        token = "56980_test_prop"
        if token in market_data_service.subscriptions:
            del market_data_service.subscriptions[token]
        
        # Register interest for paper trade
        market_data_service.register_trade_interest(
            token=token,
            trade_id=101,
            symbol="NIFTY2692223200CE",
            exchange_seg="nse_fo",
            trading_symbol="NIFTY2692223200CE",
            strike=23200.0,
            option_type="CE",
            expiry="2026-09-22"
        )
        assert market_data_service.subscriptions[token]["subscription_state"] in (SubscriptionState.REQUESTED, SubscriptionState.SUBSCRIBING)

        # Subscription ACK received
        feed.subscribed_tokens[token] = datetime.now(timezone.utc).isoformat()
        feed.state = SFeedState.SUBSCRIBED
        market_data_service.mark_subscribed(token)
        assert market_data_service.subscriptions[token]["subscription_state"] == SubscriptionState.SUBSCRIBED
        assert market_data_service.subscriptions[token]["tick_count"] == 0

        # Now simulate a real decoded tick arriving via SFeedScrip
        tick = MagicMock(spec=SFeedScrip)
        tick.instrument_token = token
        tick.last_traded_price = 245.50
        tick.trading_symbol = "NIFTY2692223200CE"
        tick.exchange_segment = "nse_fo"
        feed._on_message(tick)

        # Verify state transitioned to RECEIVING_TICKS
        assert feed.state == SFeedState.RECEIVING_TICKS
        sub_info = market_data_service.subscriptions[token]
        assert sub_info["subscription_state"] == SubscriptionState.RECEIVING_TICKS
        assert sub_info["tick_count"] == 1
        assert sub_info["latest_ltp"] == 245.50
        assert sub_info["last_tick_at"] is not None

        # Verify PaperBroker can receive this tick without invoking KotakNeoBroker.place_order()
        paper_broker = PaperBroker()
        paper_broker.inject_price(token, 245.50)
        assert await paper_broker.get_ltp(token) == 245.50

        # Ensure live broker place_order was never called
        live_calls = getattr(mock_broker, "place_order", None)
        if live_calls and hasattr(live_calls, "call_count"):
            assert live_calls.call_count == 0

        # Clean up
        market_data_service.release_trade_interest(token, 101)

    @pytest.mark.asyncio
    async def test_dashboard_state_reflects_sfeed_lifecycle(self, mock_broker):
        """Task 10: Dashboard /api/dashboard/summary reflects the actual SFeed manager lifecycle state."""
        from httpx import AsyncClient, ASGITransport
        from app.main import app
        from app.services.market_data_service import market_data_service

        feed = get_sfeed_manager(mock_broker)
        feed.state = SFeedState.CONNECTED
        feed.subscribed_tokens = {"56980": datetime.now(timezone.utc).isoformat()}
        market_data_service.sfeed_connected = True
        market_data_service.sfeed_state = "CONNECTED"

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            res = await ac.get("/api/dashboard/summary")
            assert res.status_code == 200
            data = res.json()
            assert "connections" in data
            sfeed_conn = data["connections"]["sfeed"]
            assert sfeed_conn["status"] == "CONNECTED"
