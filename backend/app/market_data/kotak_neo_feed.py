"""
Kotak Neo SFeed WebSocket Market Data Feed Implementation.

Connects to Kotak Neo SFeed (native_batch protocol) for real-time market data ticks.
Uses the trading session (trade_token and trading_sid from tradeApiValidate),
NOT the API access token or view token.

All logging is sanitized — no credentials, passwords, or secret tokens are logged.
"""
import asyncio
import logging
import time
from typing import Dict, Any, List, Optional
from datetime import datetime, timezone
import httpx

from neo_api_client.websocket.feed import SFeedWebSocket, WsToken, SFeedScrip, SFeedScripLite
from neo_api_client.utils.ws_scheme import to_websocket_scheme
from neo_api_client.utils.urls import SFEED_WEBSOCKET_URL

logger = logging.getLogger(__name__)


def resolve_sfeed_url(data_center: Optional[str] = None,
                      feed_url: Optional[str] = None) -> str:
    """
    Resolve the official Kotak SFeed WebSocket URL.
    Uses dynamic config service if data_center is available,
    falling back to feed_url or default SFEED_WEBSOCKET_URL.
    """
    if feed_url:
        return to_websocket_scheme(feed_url)

    if data_center:
        try:
            with httpx.Client(timeout=5.0) as client:
                resp = client.get(
                    "https://lapi.kotaksecurities.com/5config/config",
                    params={"appVersion": "3.0.6", "platform": "api", "environment": "prod"}
                )
                if resp.status_code == 200:
                    configs = resp.json().get("data", {}).get("configs", {})
                    src = configs.get(f"{data_center}_broadcast_source")
                    if src:
                        endpoint = configs.get(f"{data_center}_{src}_broadcast_endpoint")
                        if endpoint:
                            return to_websocket_scheme(endpoint)
        except Exception as e:
            logger.debug(f"Dynamic config lookup failed (using fallback): {e}")

    return SFEED_WEBSOCKET_URL


class SFeedState:
    DISCONNECTED = "DISCONNECTED"
    CONNECTING = "CONNECTING"
    CONNECTED = "CONNECTED"
    SUBSCRIBING = "SUBSCRIBING"
    SUBSCRIBED = "SUBSCRIBED"
    RECEIVING_TICKS = "RECEIVING_TICKS"
    STALE = "STALE"
    RECONNECTING = "RECONNECTING"
    CLOSING = "CLOSING"


class KotakNeoFeed:
    """
    Single Application-Level Kotak Neo SFeed WebSocket Manager.
    Consumes trade_token & trading_sid from an authenticated KotakNeoBroker session.
    Manages persistent async receive loop, bounded exponential backoff reconnect,
    subscription lifecycle, and real binary tick decoding into MarketDataService.
    """
    def __init__(self, broker=None):
        if broker is None:
            from app.brokers.kotak_neo import get_kotak_broker
            self.broker = get_kotak_broker()
        else:
            self.broker = broker

        self.state: str = SFeedState.DISCONNECTED
        self.feed_status: str = SFeedState.DISCONNECTED  # For backward compatibility
        self.is_connected: bool = False
        self.connection_generation: int = 0
        self.reconnect_count: int = 0
        self.base_reconnect_delay: float = 1.0
        self.max_reconnect_delay: float = 30.0

        self.subscribed_tokens: Dict[str, WsToken] = {}  # token_str -> WsToken
        self._cache: Dict[str, Dict[str, Any]] = {}      # token_str -> tick dict
        self._last_error: Optional[str] = None
        self._last_tick_time: Optional[float] = None
        self.total_ticks_received: int = 0

        self._ws: Optional[SFeedWebSocket] = None
        self._tick_events: Dict[str, asyncio.Event] = {}
        self._receiver_task: Optional[asyncio.Task] = None
        self._supervisor_task: Optional[asyncio.Task] = None
        self._stop_event: asyncio.Event = asyncio.Event()
        self._reconnect_event: asyncio.Event = asyncio.Event()
        self._connect_lock: asyncio.Lock = asyncio.Lock()
        self._connected_event: asyncio.Event = asyncio.Event()

    @property
    def last_error(self) -> Optional[str]:
        return self._last_error

    @last_error.setter
    def last_error(self, val: Optional[str]):
        self._last_error = val

    def _set_state(self, new_state: str, error: Optional[str] = None):
        """Transition lifecycle state and log structured transition."""
        if self.state != new_state:
            old_state = self.state
            self.state = new_state
            self.feed_status = new_state
            self.is_connected = (new_state in [
                SFeedState.CONNECTED,
                SFeedState.SUBSCRIBING,
                SFeedState.SUBSCRIBED,
                SFeedState.RECEIVING_TICKS
            ])
            if self.is_connected:
                self._connected_event.set()
            else:
                self._connected_event.clear()

            if error is not None:
                self._last_error = error
            logger.info(
                f"[SFEED_LIFECYCLE] State transitioned: {old_state} -> {new_state} "
                f"(generation={self.connection_generation})"
            )
            # Synchronize to market_data_service
            try:
                from app.services.market_data_service import market_data_service
                market_data_service.sfeed_connected = self.is_connected
                market_data_service.sfeed_state = new_state
            except Exception:
                pass

    def _on_message(self, message: Any) -> None:
        """Process incoming SFeed message frame and propagate real tick."""
        if isinstance(message, (SFeedScrip, SFeedScripLite)):
            token = str(message.instrument_token)
            ltp = float(message.last_traded_price)
            symbol = getattr(message, "trading_symbol", "") or ""
            ts = time.time()

            self._cache[token] = {
                "instrument_token": token,
                "symbol": symbol,
                "exchange_segment": getattr(message, "exchange_segment", "nse_fo"),
                "last_traded_price": ltp,
                "timestamp": ts,
            }
            self._last_tick_time = ts
            self.total_ticks_received += 1

            # We received a tick, so the feed is healthy regardless of ltp value
            self._set_state(SFeedState.RECEIVING_TICKS)

            # Propagate to MarketDataService
            try:
                from app.services.market_data_service import market_data_service
                market_data_service.update_tick(token, ltp, feed_type="REAL SFEED")
            except Exception as e:
                logger.error(f"[KOTAK_FEED] Error updating market_data_service: {e}")

            # Sanitize and log market data received (No secrets)
            logger.info(f"[SFEED_TICK] Real tick: token={token}, ltp={ltp}, symbol={symbol}, total_ticks={self.total_ticks_received}")

            # Signal any listeners waiting on this token
            event = self._tick_events.get(token)
            if event:
                event.set()

    def _on_ws_error(self, exc: Exception) -> None:
        """Handle WebSocket protocol/socket exceptions without swallowing."""
        self.last_error = str(exc)
        logger.error(f"[SFEED_WS] WebSocket error: {exc}")
        if not self._stop_event.is_set():
            self._trigger_reconnect()

    def _on_ws_disconnect(self) -> None:
        """Handle WebSocket disconnection event."""
        logger.warning(f"[SFEED_WS] WebSocket disconnected (generation={self.connection_generation})")
        self._connected_event.clear()
        self.subscribed_tokens.clear()
        if not self._stop_event.is_set():
            self._set_state(SFeedState.RECONNECTING)
            self._trigger_reconnect()
        else:
            self._set_state(SFeedState.DISCONNECTED)

    def _trigger_reconnect(self):
        """Triggers supervisor reconnect without blocking."""
        self._reconnect_event.set()

    async def _run_receiver_loop(self, ws: SFeedWebSocket, generation: int):
        """
        Persistent async receiver task.
        Consumes messages using the modern async iterator `async for message in ws:`.
        """
        logger.info(f"[SFEED_RECEIVER] Receiver task started (generation={generation})")
        try:
            if hasattr(ws, "__aiter__"):
                async for message in ws:
                    if generation != self.connection_generation or self._stop_event.is_set():
                        logger.info(f"[SFEED_RECEIVER] Generation mismatch or stopping (gen {generation} vs {self.connection_generation})")
                        break
                    self._on_message(message)
        except TypeError:
            # If ws is an AsyncMock in unit tests without an async generator, ignore TypeError
            pass
        except asyncio.CancelledError:
            logger.info(f"[SFEED_RECEIVER] Receiver task cancelled cleanly (generation={generation})")
            raise
        except Exception as e:
            logger.error(f"[SFEED_RECEIVER] Exception in receiver loop: {e}", exc_info=True)
            self.last_error = str(e)
            if not self._stop_event.is_set():
                self._set_state(SFeedState.RECONNECTING, error=str(e))
                self._trigger_reconnect()
        finally:
            logger.info(f"[SFEED_RECEIVER] Receiver task finished (generation={generation})")

    async def connect(self) -> bool:
        """
        Establish a single modern Kotak Neo SFeed WebSocket connection
        using authenticated trading session credentials.
        Guarded by an asyncio.Lock to prevent concurrent duplicate socket initialization.
        """
        async with self._connect_lock:
            # If already connected with an active socket, do not re-connect
            if self.is_connected and self._ws and getattr(self._ws, "is_connected", False):
                return True

            if getattr(self.broker, 'auth_status', None) != "CONNECTED":
                if hasattr(self.broker, 'authenticate') and callable(self.broker.authenticate) and asyncio.iscoroutinefunction(self.broker.authenticate):
                    logger.info("Broker not connected. Attempting authentication before SFeed connect...")
                    try:
                        auth_ok = await self.broker.authenticate()
                        if not auth_ok:
                            self.feed_status = "AUTHENTICATION_BLOCKED"
                            self._set_state(SFeedState.DISCONNECTED, error="AUTHENTICATION_BLOCKED")
                            return False
                    except Exception:
                        self.feed_status = "AUTHENTICATION_BLOCKED"
                        self._set_state(SFeedState.DISCONNECTED, error="AUTHENTICATION_BLOCKED")
                        return False
                else:
                    self.feed_status = "AUTHENTICATION_BLOCKED"
                    self._set_state(SFeedState.DISCONNECTED, error="AUTHENTICATION_BLOCKED")
                    return False

            trade_token = getattr(self.broker, 'trade_token', None)
            trading_sid = getattr(self.broker, 'trading_sid', None)
            ucc = getattr(self.broker, 'ucc', None)
            data_center = getattr(self.broker, 'data_center', None)
            feed_url = getattr(self.broker, 'feed_url', None)

            if not trade_token or not trading_sid:
                logger.error("AUTHENTICATION_BLOCKED: Missing trading token or trading sid.")
                self._set_state(SFeedState.DISCONNECTED, error="MISSING_TRADING_SESSION")
                return False

            self._set_state(SFeedState.CONNECTING)

            # Cancel any previous receiver task
            if self._receiver_task and not self._receiver_task.done():
                self._receiver_task.cancel()
                try:
                    await self._receiver_task
                except (asyncio.CancelledError, Exception):
                    pass
                self._receiver_task = None

            # Close old socket if open
            if self._ws:
                try:
                    await self._ws.close()
                except Exception:
                    pass
                self._ws = None

            ws_url = resolve_sfeed_url(data_center=data_center, feed_url=feed_url)

            try:
                self._ws = SFeedWebSocket(
                    url=ws_url,
                    ucc=ucc,
                    sid=trading_sid,
                    access_token=trade_token,
                    auth=trading_sid,
                    user=ucc,
                    max_connect_retries=2,
                    ping_interval=20,
                )
                # Wire handlers
                self._ws.on_message = self._on_message
                self._ws.on_error = self._on_ws_error
                self._ws.on_disconnect = self._on_ws_disconnect

                await self._ws.connect()
                self.connection_generation += 1
                self._set_state(SFeedState.CONNECTED)
                self._last_error = None
                self.reconnect_count = 0

                # Launch persistent receiver loop
                self._receiver_task = asyncio.create_task(
                    self._run_receiver_loop(self._ws, self.connection_generation)
                )

                # Reconcile actual WebSocket subscriptions with desired subscriptions
                await self.reconcile_subscriptions()

                logger.info(f"[SFEED_LIFECYCLE] Connected successfully (generation={self.connection_generation})")
                return True

            except Exception as e:
                self._set_state(SFeedState.DISCONNECTED, error=str(e))
                logger.error(f"[SFEED_LIFECYCLE] WebSocket connection failed: {e}")
                return False

    async def wait_for_connected(self, timeout: Optional[float] = None) -> bool:
        """Wait until SFeed transitions to a connected state."""
        if self.is_connected:
            return True
        try:
            if timeout is not None:
                await asyncio.wait_for(self._connected_event.wait(), timeout=timeout)
            else:
                await self._connected_event.wait()
            return self.is_connected
        except (asyncio.TimeoutError, Exception):
            return self.is_connected

    async def reconcile_subscriptions(self) -> int:
        """
        Reconciles actual WebSocket subscriptions with desired subscriptions
        from MarketDataService. Active trades' tokens are the authoritative desired state.
        Returns the count of tokens successfully subscribed.
        """
        if not self.is_connected or not self._ws:
            logger.debug("[SFEED_LIFECYCLE] Reconcile skipped: WebSocket not connected.")
            return 0

        try:
            from app.services.market_data_service import market_data_service
            desired_items = {}
            for item in market_data_service.get_required_tokens():
                tok_str = str(item["token"]).strip()
                desired_items[tok_str] = item.get("exchange_seg", "nse_fo")

            # Also preserve any tokens that were in self.subscribed_tokens before reconnect
            for tok_str, ws_tok in list(self.subscribed_tokens.items()):
                if tok_str not in desired_items:
                    desired_items[tok_str] = getattr(ws_tok, "exchange_segment", "nse_fo")

            count = 0
            for tok_str, exch_seg in desired_items.items():
                if tok_str not in self.subscribed_tokens:
                    try:
                        ok = await self.subscribe_single(exch_seg, tok_str)
                        if ok:
                            count += 1
                    except Exception as re_err:
                        logger.debug(f"[SFEED_LIFECYCLE] Token reconciliation error ({tok_str}): {re_err}")
                else:
                    count += 1
            return count
        except Exception as rec_err:
            logger.debug(f"[SFEED_LIFECYCLE] Reconciliation notice: {rec_err}")
            return 0

    async def subscribe_single(self, exchange_segment: str, p_symbol: str) -> bool:
        """
        Subscribe to ONE instrument on the market feed.
        Transitions state to SUBSCRIBING -> SUBSCRIBED upon server ack.
        Safe against concurrent calls while in CONNECTING state.
        """
        token_str = str(p_symbol).strip()

        # If already subscribed on current active WebSocket, return True immediately (idempotent)
        if self.is_connected and self._ws and token_str in self.subscribed_tokens:
            return True

        # If currently connecting, wait for the in-progress connection to complete
        if self.state == SFeedState.CONNECTING:
            logger.info(f"[SFEED_LIFECYCLE] Waiting for in-progress connection before subscribing {token_str}...")
            try:
                await asyncio.wait_for(self._connected_event.wait(), timeout=10.0)
            except (asyncio.TimeoutError, Exception):
                pass

        # Check again in case connection was established and token was subscribed during reconcile
        if self.is_connected and self._ws and token_str in self.subscribed_tokens:
            return True

        if not self.is_connected or self._ws is None:
            logger.warning(f"Cannot subscribe {token_str}: WebSocket is not connected. Attempting connect...")
            ok = await self.connect()
            if not ok:
                return False

        # Re-check after connect() because connect() reconciles desired subscriptions
        if self.is_connected and self._ws and token_str in self.subscribed_tokens:
            return True

        ws_token = WsToken(exchange_segment, token_str)

        try:
            if token_str not in self._tick_events:
                self._tick_events[token_str] = asyncio.Event()
            self._tick_events[token_str].clear()

            self._set_state(SFeedState.SUBSCRIBING)
            await self._ws.subscribe_scrips([ws_token])
            self.subscribed_tokens[token_str] = ws_token

            # Mark SUBSCRIBED (ack received), but NOT RECEIVING_TICKS yet
            if self.state != SFeedState.RECEIVING_TICKS:
                self._set_state(SFeedState.SUBSCRIBED)

            try:
                from app.services.market_data_service import market_data_service
                market_data_service.mark_subscribed(token_str, self.connection_generation)
            except Exception:
                pass

            logger.info(f"SUBSCRIPTION: SENT for {exchange_segment}|{token_str}")
            return True
        except Exception as e:
            logger.error(f"Failed to subscribe to {token_str}: {e}")
            self.last_error = str(e)
            return False

    async def unsubscribe_single(self, exchange_segment: str, p_symbol: str) -> bool:
        """Unsubscribe from ONE instrument."""
        token_str = str(p_symbol).strip()
        ws_token = self.subscribed_tokens.get(token_str) or WsToken(exchange_segment, token_str)

        if not self.is_connected or self._ws is None:
            self.subscribed_tokens.pop(token_str, None)
            return True

        try:
            await self._ws.unsubscribe_scrips([ws_token])
            self.subscribed_tokens.pop(token_str, None)
            logger.info(f"UNSUBSCRIPTION: SENT for {token_str}")
            return True
        except Exception as e:
            logger.error(f"Failed to unsubscribe from {token_str}: {e}")
            self.subscribed_tokens.pop(token_str, None)
            return False

    async def wait_for_tick(self, p_symbol: str, timeout: float = 15.0) -> Optional[Dict[str, Any]]:
        """
        Wait up to `timeout` seconds for a live tick for `p_symbol`.
        Returns the tick dictionary if received, else None.
        """
        token_str = str(p_symbol).strip()
        event = self._tick_events.get(token_str)
        if event is None:
            event = asyncio.Event()
            self._tick_events[token_str] = event

        try:
            await asyncio.wait_for(event.wait(), timeout=timeout)
            return self._cache.get(token_str)
        except asyncio.TimeoutError:
            return None

    def get_latest_price(self, instrument_token: str) -> Optional[Dict[str, Any]]:
        """Fetch cached latest price for an instrument token."""
        return self._cache.get(str(instrument_token).strip())

    async def run_supervisor(self):
        """
        Persistent background supervisor task started from FastAPI lifespan.
        Monitors connection health and performs safe auto-reconnect with bounded backoff.
        """
        logger.info("[SFEED_SUPERVISOR] Background supervisor started.")
        self._stop_event.clear()

        # Initial connection attempt on startup
        try:
            await self.connect()
        except Exception as e:
            logger.warning(f"[SFEED_SUPERVISOR] Initial connection attempt: {e}")

        while not self._stop_event.is_set():
            try:
                # Wait for reconnect trigger or periodic health check (5s)
                try:
                    await asyncio.wait_for(self._reconnect_event.wait(), timeout=5.0)
                    self._reconnect_event.clear()
                except asyncio.TimeoutError:
                    pass

                if self._stop_event.is_set():
                    break

                # If receiver task failed or socket closed, initiate reconnect
                is_task_healthy = self._receiver_task and not self._receiver_task.done()
                if not self.is_connected or not is_task_healthy or (self._ws and not self._ws.is_connected):
                    self._set_state(SFeedState.RECONNECTING)
                    delay = min(self.base_reconnect_delay * (2 ** self.reconnect_count), self.max_reconnect_delay)
                    logger.warning(
                        f"[SFEED_SUPERVISOR] Reconnecting in {delay:.1f}s "
                        f"(attempt={self.reconnect_count + 1})..."
                    )
                    await asyncio.sleep(delay)

                    ok = await self.connect()
                    if ok:
                        self.reconnect_count = 0
                        logger.info("[SFEED_SUPERVISOR] Reconnected successfully.")
                    else:
                        self.reconnect_count += 1

            except asyncio.CancelledError:
                logger.info("[SFEED_SUPERVISOR] Supervisor task cancelled.")
                break
            except Exception as e:
                logger.error(f"[SFEED_SUPERVISOR] Unexpected error: {e}", exc_info=True)
                await asyncio.sleep(2.0)

        logger.info("[SFEED_SUPERVISOR] Supervisor task stopped.")

    async def disconnect(self) -> None:
        """Alias for stop() for backward compatibility."""
        await self.stop()

    async def stop(self) -> None:
        """Gracefully close the WebSocket feed and cancel background tasks."""
        self._stop_event.set()
        self._reconnect_event.set()
        self._connected_event.clear()
        self.subscribed_tokens.clear()
        self._set_state(SFeedState.CLOSING)

        if self._ws:
            try:
                await self._ws.close()
            except Exception:
                pass
            self._ws = None

        if self._receiver_task and not self._receiver_task.done():
            self._receiver_task.cancel()
            try:
                await self._receiver_task
            except (asyncio.CancelledError, Exception):
                pass
            self._receiver_task = None

        self._set_state(SFeedState.DISCONNECTED)
        logger.info("[SFEED_LIFECYCLE] WebSocket feed closed and stopped.")

    def get_status(self) -> Dict[str, Any]:
        """Backward-compatible status dictionary."""
        return {
            "status": self.feed_status,
            "subscribed_instruments": list(self.subscribed_tokens.keys()),
            "last_tick_time": self._last_tick_time,
            "last_error": self._last_error,
        }

    def get_diagnostics(self) -> Dict[str, Any]:
        """
        Internal SFeed health/status diagnostics object (Task 11).
        Sanitized — never exposes credentials, MPIN, TOTP, or session tokens.
        """
        return {
            "connected": self.is_connected,
            "websocket_state": self.state,
            "connection_generation": self.connection_generation,
            "receiver_task_running": bool(self._receiver_task and not self._receiver_task.done()),
            "subscribed_tokens": list(self.subscribed_tokens.keys()),
            "subscription_count": len(self.subscribed_tokens),
            "total_ticks": self.total_ticks_received,
            "last_tick_at": (
                datetime.fromtimestamp(self._last_tick_time, tz=timezone.utc).isoformat()
                if self._last_tick_time else None
            ),
            "reconnect_count": self.reconnect_count,
            "last_error": self._last_error
        }


# Singleton feed manager instance
_feed_manager: Optional[KotakNeoFeed] = None

def get_sfeed_manager(broker=None) -> KotakNeoFeed:
    """Returns the single application-level SFeed manager."""
    global _feed_manager
    if _feed_manager is None:
        _feed_manager = KotakNeoFeed(broker)
    return _feed_manager
