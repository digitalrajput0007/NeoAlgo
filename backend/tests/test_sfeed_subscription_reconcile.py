"""
NEOALGO — SFEED SUBSCRIPTION LIFECYCLE RECONCILIATION TESTS
Tests covering:
1. Subscription requested while DISCONNECTED -> connects & subscribes
2. Subscription requested while CONNECTING -> waits for connection, avoids duplicate connect
3. Startup active trade exists before SFeed connects -> auto-subscribed on connect
4. Connection fails during startup -> active trade persisted, FastAPI runs, retries
5. Reconnect with active trade -> auto-resubscribes token
6. Reconnect with multiple active tokens -> all desired tokens resubscribed
7. Reconnect with same token used by multiple trades -> exactly one subscription, ref count preserved
8. Closing one of multiple trades -> token remains subscribed
9. Closing final trade -> token unsubscribed
10. Duplicate reconnect/subscription attempts -> idempotent, no duplicate
11. Realistic end-to-end: active trade 56980 -> connection -> subscription -> tick -> latest_ltp updated
"""
import pytest
import asyncio
from unittest.mock import MagicMock, AsyncMock, patch

from app.market_data.kotak_neo_feed import KotakNeoFeed, SFeedState
from app.services.market_data_service import (
    MarketDataService,
    SubscriptionState,
    market_data_service,
)
from neo_api_client.websocket.feed import SFeedScrip, WsToken


@pytest.fixture(autouse=True)
def clean_market_data_singleton():
    """Ensure clean subscription state between tests."""
    market_data_service.subscriptions.clear()
    market_data_service._price_listeners.clear()
    market_data_service.total_ticks_received = 0
    yield
    market_data_service.subscriptions.clear()
    market_data_service._price_listeners.clear()
    market_data_service.total_ticks_received = 0


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


class TestSFeedSubscriptionReconcile:

    # 1. Subscription requested while DISCONNECTED -> connection established, subscription succeeds.
    @pytest.mark.asyncio
    async def test_1_subscribe_while_disconnected(self, mock_broker):
        feed = KotakNeoFeed(mock_broker)
        assert feed.state == SFeedState.DISCONNECTED

        with patch("app.market_data.kotak_neo_feed.SFeedWebSocket") as mock_ws_cls:
            mock_ws = AsyncMock()
            mock_ws_cls.return_value = mock_ws

            sub_ok = await feed.subscribe_single("nse_fo", "56980")
            assert sub_ok is True
            assert feed.is_connected is True
            assert "56980" in feed.subscribed_tokens
            mock_ws.connect.assert_awaited_once()
            mock_ws.subscribe_scrips.assert_awaited()

    # 2. Subscription requested while CONNECTING -> waits for existing connection, does not duplicate.
    @pytest.mark.asyncio
    async def test_2_subscribe_while_connecting_waits(self, mock_broker):
        feed = KotakNeoFeed(mock_broker)

        with patch("app.market_data.kotak_neo_feed.SFeedWebSocket") as mock_ws_cls:
            mock_ws = AsyncMock()
            mock_ws_cls.return_value = mock_ws

            # Simulate connect in progress
            feed._set_state(SFeedState.CONNECTING)

            async def delayed_complete_connect():
                await asyncio.sleep(0.05)
                feed._ws = mock_ws
                feed._set_state(SFeedState.CONNECTED)

            asyncio.create_task(delayed_complete_connect())

            # subscribe_single called while CONNECTING
            sub_ok = await feed.subscribe_single("nse_fo", "56980")
            assert sub_ok is True
            assert "56980" in feed.subscribed_tokens
            # Should not have called connect again
            assert mock_ws.connect.call_count == 0

    # 3. Startup active trade exists before SFeed connects -> SFeed connects -> active token auto subscribed.
    @pytest.mark.asyncio
    async def test_3_startup_active_trade_auto_subscribed_on_connect(self, mock_broker):
        # Trade registered before SFeed is connected
        market_data_service.register_trade_interest(
            token="56980",
            trade_id=101,
            symbol="NIFTY2692223200CE",
            exchange_seg="nse_fo",
        )
        assert "56980" in market_data_service.subscriptions

        feed = KotakNeoFeed(mock_broker)
        assert "56980" not in feed.subscribed_tokens

        with patch("app.market_data.kotak_neo_feed.SFeedWebSocket") as mock_ws_cls:
            mock_ws = AsyncMock()
            mock_ws_cls.return_value = mock_ws

            connect_ok = await feed.connect()
            assert connect_ok is True
            assert "56980" in feed.subscribed_tokens
            mock_ws.subscribe_scrips.assert_awaited()

    # 4. Connection fails during startup -> active trade remains persisted, supervisor retries.
    @pytest.mark.asyncio
    async def test_4_connection_fails_trade_remains_persisted(self, mock_broker):
        market_data_service.register_trade_interest(
            token="56980",
            trade_id=102,
            symbol="NIFTY2692223200CE",
            exchange_seg="nse_fo",
        )
        assert "56980" in market_data_service.subscriptions

        feed = KotakNeoFeed(mock_broker)
        with patch("app.market_data.kotak_neo_feed.SFeedWebSocket") as mock_ws_cls:
            mock_ws = AsyncMock()
            mock_ws.connect.side_effect = ConnectionError("Kotak unreachable")
            mock_ws_cls.return_value = mock_ws

            connect_ok = await feed.connect()
            assert connect_ok is False
            assert feed.is_connected is False
            # Crucial: active trade interest is NOT deleted
            assert "56980" in market_data_service.subscriptions
            assert 102 in market_data_service.subscriptions["56980"]["active_trade_ids"]

    # 5. Reconnect with active trade -> token is automatically resubscribed.
    @pytest.mark.asyncio
    async def test_5_reconnect_with_active_trade(self, mock_broker):
        market_data_service.register_trade_interest("56980", trade_id=201)
        feed = KotakNeoFeed(mock_broker)

        with patch("app.market_data.kotak_neo_feed.SFeedWebSocket") as mock_ws_cls:
            mock_ws_1 = AsyncMock()
            mock_ws_cls.return_value = mock_ws_1
            await feed.connect()
            assert "56980" in feed.subscribed_tokens

            # Simulate disconnect
            feed._on_ws_disconnect()
            assert len(feed.subscribed_tokens) == 0
            # Desired state still in market_data_service
            assert "56980" in market_data_service.subscriptions

            # Reconnect with second websocket
            mock_ws_2 = AsyncMock()
            mock_ws_cls.return_value = mock_ws_2
            await feed.connect()
            assert "56980" in feed.subscribed_tokens
            mock_ws_2.subscribe_scrips.assert_awaited()

    # 6. Reconnect with multiple active tokens -> all desired tokens resubscribed.
    @pytest.mark.asyncio
    async def test_6_reconnect_multiple_tokens(self, mock_broker):
        market_data_service.register_trade_interest("56980", trade_id=301)
        market_data_service.register_trade_interest("56984", trade_id=302)
        market_data_service.register_trade_interest("57000", trade_id=303)

        feed = KotakNeoFeed(mock_broker)
        with patch("app.market_data.kotak_neo_feed.SFeedWebSocket") as mock_ws_cls:
            mock_ws = AsyncMock()
            mock_ws_cls.return_value = mock_ws

            await feed.connect()
            assert "56980" in feed.subscribed_tokens
            assert "56984" in feed.subscribed_tokens
            assert "57000" in feed.subscribed_tokens

    # 7. Reconnect with same token used by multiple trades -> exactly one subscription, ref count preserved.
    @pytest.mark.asyncio
    async def test_7_reconnect_same_token_multiple_trades(self, mock_broker):
        market_data_service.register_trade_interest("56980", trade_id=401)
        market_data_service.register_trade_interest("56980", trade_id=402)
        market_data_service.register_trade_interest("56980", trade_id=403)

        assert len(market_data_service.subscriptions["56980"]["active_trade_ids"]) == 3

        feed = KotakNeoFeed(mock_broker)
        with patch("app.market_data.kotak_neo_feed.SFeedWebSocket") as mock_ws_cls:
            mock_ws = AsyncMock()
            mock_ws_cls.return_value = mock_ws

            await feed.connect()
            # Exactly one actual subscription in feed
            assert len(feed.subscribed_tokens) == 1
            assert "56980" in feed.subscribed_tokens
            # Reference count in MarketDataService preserved
            assert len(market_data_service.subscriptions["56980"]["active_trade_ids"]) == 3

    # 8. Closing one of multiple trades -> token remains subscribed.
    @pytest.mark.asyncio
    async def test_8_closing_one_of_multiple_trades_keeps_subscription(self, mock_broker):
        market_data_service.register_trade_interest("56980", trade_id=501)
        market_data_service.register_trade_interest("56980", trade_id=502)

        feed = KotakNeoFeed(mock_broker)
        with patch("app.market_data.kotak_neo_feed.SFeedWebSocket") as mock_ws_cls:
            mock_ws = AsyncMock()
            mock_ws_cls.return_value = mock_ws
            await feed.connect()
            assert "56980" in feed.subscribed_tokens

            # Trade 501 closes
            market_data_service.release_trade_interest("56980", trade_id=501)
            # Token MUST remain subscribed
            assert "56980" in market_data_service.subscriptions
            assert len(market_data_service.subscriptions["56980"]["active_trade_ids"]) == 1
            assert "56980" in feed.subscribed_tokens

    # 9. Closing final trade -> token unsubscribed.
    @pytest.mark.asyncio
    async def test_9_closing_final_trade_unsubscribes(self, mock_broker):
        market_data_service.register_trade_interest("56980", trade_id=601)

        feed = KotakNeoFeed(mock_broker)
        with patch("app.market_data.kotak_neo_feed.SFeedWebSocket") as mock_ws_cls:
            mock_ws = AsyncMock()
            mock_ws_cls.return_value = mock_ws
            await feed.connect()
            assert "56980" in feed.subscribed_tokens

            # Final trade closes
            market_data_service.release_trade_interest("56980", trade_id=601)
            assert "56980" not in market_data_service.subscriptions

    # 10. Duplicate reconnect/subscription attempts -> idempotent, no duplicate actual subscription.
    @pytest.mark.asyncio
    async def test_10_duplicate_subscription_is_idempotent(self, mock_broker):
        feed = KotakNeoFeed(mock_broker)
        with patch("app.market_data.kotak_neo_feed.SFeedWebSocket") as mock_ws_cls:
            mock_ws = AsyncMock()
            mock_ws_cls.return_value = mock_ws
            await feed.connect()

            # First subscription
            res1 = await feed.subscribe_single("nse_fo", "56980")
            assert res1 is True
            initial_call_count = mock_ws.subscribe_scrips.call_count

            # Duplicate subscription
            res2 = await feed.subscribe_single("nse_fo", "56980")
            assert res2 is True
            # Should NOT send another wire frame
            assert mock_ws.subscribe_scrips.call_count == initial_call_count

    # 11. Realistic end-to-end: active trade token 56980 -> connection -> subscription -> tick -> latest_ltp updated.
    @pytest.mark.asyncio
    async def test_11_realistic_e2e_token_56980_tick_flow(self, mock_broker):
        # Register active trade on token 56980
        market_data_service.register_trade_interest(
            token="56980",
            trade_id=701,
            symbol="NIFTY2692223200CE",
            exchange_seg="nse_fo",
        )
        assert market_data_service.subscriptions["56980"]["latest_ltp"] is None

        feed = KotakNeoFeed(mock_broker)
        with patch("app.market_data.kotak_neo_feed.SFeedWebSocket") as mock_ws_cls:
            mock_ws = AsyncMock()
            mock_ws_cls.return_value = mock_ws

            # 1. Connect and auto-reconcile
            await feed.connect()
            assert "56980" in feed.subscribed_tokens

            # 2. Simulated binary tick arrives
            tick = MagicMock(spec=SFeedScrip)
            tick.instrument_token = "56980"
            tick.last_traded_price = 179.10
            tick.trading_symbol = "NIFTY2692223200CE"
            tick.exchange_segment = "nse_fo"

            feed._on_message(tick)

            # 3. Assertions
            assert feed.state == SFeedState.RECEIVING_TICKS
            assert feed.total_ticks_received == 1
            sub = market_data_service.subscriptions["56980"]
            assert sub["latest_ltp"] == 179.10
            assert sub["tick_count"] == 1
            assert sub["feed_status"] == "RECEIVING_TICKS"
            assert sub["feed_type"] == "REAL SFEED"
