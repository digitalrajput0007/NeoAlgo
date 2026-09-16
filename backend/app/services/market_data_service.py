import asyncio
import logging
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional, Callable, Set

logger = logging.getLogger(__name__)


class SubscriptionState:
    REQUESTED = "REQUESTED"
    SUBSCRIBING = "SUBSCRIBING"
    SUBSCRIBED = "SUBSCRIBED"
    RECEIVING_TICKS = "RECEIVING_TICKS"
    STALE = "STALE"
    UNSUBSCRIBING = "UNSUBSCRIBING"


class MarketDataService:
    """
    Unified Market Data Service.
    Single source of truth for active instrument subscriptions and live ticks.
    Enforces reference counting across multiple trades sharing instruments,
    tracks separate subscription ACK vs first real market tick,
    and distinguishes REAL SFEED from TEST DATA clearly.
    """
    _instance = None

    def __init__(self):
        self.subscriptions: Dict[str, Dict[str, Any]] = {}
        self._price_listeners: List[Callable[[str, float], Any]] = []
        self.total_ticks_received: int = 0
        self.last_tick_timestamp: Optional[str] = None
        self.sfeed_connected: bool = False
        self.sfeed_state: str = "DISCONNECTED"

    @classmethod
    def get_instance(cls) -> "MarketDataService":
        if cls._instance is None:
            cls._instance = MarketDataService()
        return cls._instance

    def register_listener(self, callback: Callable[[str, float], Any]):
        if callback not in self._price_listeners:
            self._price_listeners.append(callback)

    def subscribe(
        self,
        instrument_token: str,
        symbol: str = "",
        exchange_seg: str = "nse_fo",
        trading_symbol: str = "",
        strike: float = 0.0,
        option_type: str = "",
        expiry: str = "",
        initial_ltp: Optional[float] = None,
        feed_type: str = "PENDING SFEED"
    ):
        """Backward-compatible registration of an instrument subscription."""
        tok = str(instrument_token).strip()
        now_str = datetime.now(timezone.utc).isoformat()

        if tok not in self.subscriptions:
            self.subscriptions[tok] = {
                "instrument_token": tok,
                "pSymbol": symbol or tok,
                "pExchSeg": exchange_seg,
                "pTrdSymbol": trading_symbol or symbol or tok,
                "strike": strike,
                "option_type": option_type,
                "expiry": expiry,
                "latest_ltp": initial_ltp,
                "last_tick": now_str if initial_ltp is not None else None,
                "first_tick_at": now_str if initial_ltp is not None else None,
                "created_at": now_str,
                "subscribed_at": None,
                "feed_type": feed_type,
                "feed_status": "RECEIVING_TICKS" if initial_ltp is not None else "SUBSCRIBED" if self.sfeed_connected else "CONNECTING",
                "subscription_state": SubscriptionState.RECEIVING_TICKS if initial_ltp is not None else SubscriptionState.REQUESTED,
                "tick_count": 1 if initial_ltp is not None else 0,
                "connection_generation": 0,
                "active_trade_ids": set(),
                "error": None
            }
            logger.info(f"[MARKET_DATA] Subscribed: {tok} ({feed_type})")
        else:
            sub = self.subscriptions[tok]
            if symbol: sub["pSymbol"] = symbol
            if trading_symbol: sub["pTrdSymbol"] = trading_symbol
            if strike: sub["strike"] = strike
            if option_type: sub["option_type"] = option_type
            if expiry: sub["expiry"] = expiry
            if initial_ltp is not None:
                sub["latest_ltp"] = initial_ltp
                sub["last_tick"] = now_str
                sub["feed_type"] = feed_type
                sub["tick_count"] = sub.get("tick_count", 0) + 1
                sub["subscription_state"] = SubscriptionState.RECEIVING_TICKS
                sub["feed_status"] = "RECEIVING_TICKS"

    def register_trade_interest(
        self,
        token: str,
        trade_id: int,
        symbol: str = "",
        exchange_seg: str = "nse_fo",
        trading_symbol: str = "",
        strike: float = 0.0,
        option_type: str = "",
        expiry: str = ""
    ):
        """
        Registers a trade's interest in an instrument token (Reference Counting).
        Subscribes to SFeed if not already active.
        """
        tok = str(token).strip()
        now_str = datetime.now(timezone.utc).isoformat()

        if tok not in self.subscriptions:
            self.subscriptions[tok] = {
                "instrument_token": tok,
                "pSymbol": symbol or tok,
                "pExchSeg": exchange_seg,
                "pTrdSymbol": trading_symbol or symbol or tok,
                "strike": strike,
                "option_type": option_type,
                "expiry": expiry,
                "latest_ltp": None,
                "last_tick": None,
                "first_tick_at": None,
                "created_at": now_str,
                "subscribed_at": None,
                "feed_type": "PENDING SFEED",
                "feed_status": "SUBSCRIBING" if self.sfeed_connected else "CONNECTING",
                "subscription_state": SubscriptionState.REQUESTED,
                "tick_count": 0,
                "connection_generation": 0,
                "active_trade_ids": {trade_id},
                "error": None
            }
            logger.info(f"[MARKET_DATA] Registered trade #{trade_id} interest for token {tok} (new subscription)")
            # Trigger SFeed subscription if event loop is running
            try:
                loop = asyncio.get_running_loop()
                from app.market_data.kotak_neo_feed import get_sfeed_manager
                sfeed = get_sfeed_manager()
                loop.create_task(sfeed.subscribe_single(exchange_seg, tok))
            except (RuntimeError, Exception) as e:
                logger.debug(f"[MARKET_DATA] SFeed auto-subscribe notice: {e}")
        else:
            sub = self.subscriptions[tok]
            sub["active_trade_ids"].add(trade_id)
            if symbol: sub["pSymbol"] = symbol
            if trading_symbol: sub["pTrdSymbol"] = trading_symbol
            if strike: sub["strike"] = strike
            if option_type: sub["option_type"] = option_type
            if expiry: sub["expiry"] = expiry
            logger.info(f"[MARKET_DATA] Registered trade #{trade_id} interest for token {tok} (ref count={len(sub['active_trade_ids'])})")

    def release_trade_interest(self, token: str, trade_id: int):
        """
        Releases a trade's interest in an instrument token.
        Only unsubscribes from SFeed when reference count drops to zero.
        """
        tok = str(token).strip()
        sub = self.subscriptions.get(tok)
        if not sub:
            return

        sub["active_trade_ids"].discard(trade_id)
        remaining = len(sub["active_trade_ids"])
        logger.info(f"[MARKET_DATA] Released trade #{trade_id} interest for token {tok} (remaining refs={remaining})")

        if remaining == 0:
            sub["subscription_state"] = SubscriptionState.UNSUBSCRIBING
            sub["feed_status"] = "UNSUBSCRIBING"
            # Unsubscribe from SFeed if event loop is running
            try:
                loop = asyncio.get_running_loop()
                from app.market_data.kotak_neo_feed import get_sfeed_manager
                sfeed = get_sfeed_manager()
                loop.create_task(sfeed.unsubscribe_single(sub["pExchSeg"], tok))
            except (RuntimeError, Exception) as e:
                logger.debug(f"[MARKET_DATA] SFeed auto-unsubscribe notice: {e}")
            del self.subscriptions[tok]
            logger.info(f"[MARKET_DATA] Final trade closed for token {tok} — unsubscribed.")

    def mark_subscribed(self, instrument_token: str, generation: int = 0):
        """Called when SFeed server acknowledges the subscription."""
        tok = str(instrument_token).strip()
        sub = self.subscriptions.get(tok)
        if sub:
            now_str = datetime.now(timezone.utc).isoformat()
            sub["subscribed_at"] = now_str
            sub["connection_generation"] = generation
            if sub["subscription_state"] != SubscriptionState.RECEIVING_TICKS:
                sub["subscription_state"] = SubscriptionState.SUBSCRIBED
                sub["feed_status"] = "SUBSCRIBED"
                sub["feed_type"] = "REAL SFEED"
            logger.info(f"[MARKET_DATA] Subscription acknowledged for token {tok} (generation={generation})")

    def unsubscribe(self, instrument_token: str):
        """Force removes an instrument subscription from market data service."""
        tok = str(instrument_token).strip()
        if tok in self.subscriptions:
            sub = self.subscriptions.pop(tok)
            try:
                from app.market_data.kotak_neo_feed import get_sfeed_manager
                sfeed = get_sfeed_manager()
                asyncio.create_task(sfeed.unsubscribe_single(sub.get("pExchSeg", "nse_fo"), tok))
            except Exception:
                pass
            logger.info(f"[MARKET_DATA] Unsubscribed: {tok}")

    def update_tick(self, instrument_token: str, ltp: float, feed_type: str = "REAL SFEED"):
        """Records a new market tick and notifies listeners."""
        self.total_ticks_received += 1
        now_str = datetime.now(timezone.utc).isoformat()
        self.last_tick_timestamp = now_str
        tok = str(instrument_token).strip()

        if tok in self.subscriptions:
            sub = self.subscriptions[tok]
            sub["latest_ltp"] = ltp
            sub["last_tick"] = now_str
            sub["last_tick_at"] = now_str
            if not sub.get("first_tick_at"):
                sub["first_tick_at"] = now_str
            sub["tick_count"] = sub.get("tick_count", 0) + 1
            sub["feed_type"] = feed_type
            sub["subscription_state"] = SubscriptionState.RECEIVING_TICKS
            sub["feed_status"] = "RECEIVING_TICKS"
            sub["is_stale"] = False
        else:
            self.subscribe(
                instrument_token=tok,
                initial_ltp=ltp,
                feed_type=feed_type
            )

        # Notify any async listeners (e.g. TradeManager)
        for listener in self._price_listeners:
            try:
                res = listener(tok, ltp)
                if asyncio.iscoroutine(res):
                    asyncio.create_task(res)
            except Exception as e:
                logger.error(f"[MARKET_DATA] Error in price listener: {e}")

    def is_stale(self, instrument_token: str, max_age_seconds: Optional[int] = None) -> bool:
        """
        Determines if market data for an instrument is stale.
        Returns True if no tick received within threshold or last tick is older than threshold.
        """
        if max_age_seconds is None:
            from app.config import settings
            max_age_seconds = getattr(settings, "market_data_stale_timeout_seconds", 60)

        tok = str(instrument_token).strip()
        sub = self.subscriptions.get(tok)
        if not sub:
            return False

        now = datetime.now(timezone.utc)

        # If no tick ever arrived, check age since subscription
        if not sub.get("last_tick"):
            ref_time_str = sub.get("subscribed_at") or sub.get("created_at")
            if ref_time_str:
                try:
                    ref_dt = datetime.fromisoformat(ref_time_str)
                    if (now - ref_dt).total_seconds() > max_age_seconds:
                        sub["subscription_state"] = SubscriptionState.STALE
                        sub["feed_status"] = "STALE"
                        sub["is_stale"] = True
                        return True
                except Exception:
                    pass
            return False

        try:
            last_tick_dt = datetime.fromisoformat(sub["last_tick"])
            age = (now - last_tick_dt).total_seconds()
            stale_status = age > max_age_seconds
            sub["is_stale"] = stale_status
            if stale_status:
                sub["subscription_state"] = SubscriptionState.STALE
                sub["feed_status"] = "STALE"
            elif not stale_status and sub.get("feed_status") == "STALE":
                sub["subscription_state"] = SubscriptionState.RECEIVING_TICKS
                sub["feed_status"] = "RECEIVING_TICKS"
            return stale_status
        except Exception:
            return True

    def get_required_tokens(self) -> List[Dict[str, str]]:
        """Returns active tokens that must be re-subscribed on SFeed reconnect."""
        required = []
        for tok, sub in self.subscriptions.items():
            active_ids = sub.get("active_trade_ids", set())
            if len(active_ids) > 0 and sub.get("feed_status") != "CLOSED":
                required.append({
                    "token": tok,
                    "exchange_seg": sub.get("pExchSeg", "nse_fo")
                })
        return required

    def get_subscriptions(self) -> List[Dict[str, Any]]:
        # Update stale flags on active subscriptions
        for tok in self.subscriptions:
            self.is_stale(tok)
        return list(self.subscriptions.values())

    def get_status(self) -> Dict[str, Any]:
        return {
            "sfeed_connected": self.sfeed_connected,
            "feed_status": self.sfeed_state,
            "active_subscriptions": len(self.subscriptions),
            "total_ticks": self.total_ticks_received,
            "last_tick_time": self.last_tick_timestamp
        }


market_data_service = MarketDataService.get_instance()
