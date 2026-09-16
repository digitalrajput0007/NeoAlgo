from typing import Any, Dict, List
import uuid
import logging
from datetime import datetime, timezone
from app.brokers.base import BrokerInterface

logger = logging.getLogger(__name__)

class PaperBroker(BrokerInterface):
    """
    Simulated broker for Paper Trading mode.
    Does NOT connect to any real exchange.
    """
    def __init__(self, simulator_mode: bool = False):
        self.simulator_mode = simulator_mode
        self._positions = []
        self._orders = []
        self._injected_prices = {} # instrument_token -> price

    def inject_price(self, instrument_token: str, price: float):
        self._injected_prices[instrument_token] = price
        logger.info(f"[PAPER] Injected price for {instrument_token}: {price}")

    async def authenticate(self) -> bool:
        logger.info("[PAPER] Authenticated")
        return True

    async def get_profile(self) -> Dict[str, Any]:
        return {"name": "Paper Trader", "balance": 100000.0}

    async def get_instruments(self) -> List[Dict[str, Any]]:
        return []

    async def resolve_option_contract(self, underlying: str, strike: float, option_type: str, expiry: str) -> Dict[str, Any]:
        # Only simulator / explicit test underlyings use test tokens
        if self.simulator_mode or underlying.startswith("PAPER_") or underlying.startswith("TEST_"):
            token = f"PAPER_{underlying}_{strike}_{option_type}_{expiry}" if not underlying.startswith("PAPER_") else f"{underlying}_{strike}_{option_type}_{expiry}"
            logger.info(f"[PAPER] Resolved test simulator contract: {token}")
            return {"instrument_token": token, "symbol": token, "exchange_segment": "nse_fo", "lot_size": 75}

        # Real underlyings (NIFTY, BANKNIFTY, etc.) MUST use the official Scrip Master
        from app.market_data.instrument_resolver import InstrumentResolver
        resolver = InstrumentResolver()
        resolver.initialize()
        return await resolver.resolve_option_contract(underlying, strike, option_type, expiry)

    async def get_ltp(self, instrument_token: str) -> float:
        return self._injected_prices.get(instrument_token, 0.0)

    async def get_quote(self, instrument_token: str) -> Dict[str, Any]:
        return {"ltp": await self.get_ltp(instrument_token)}

    async def get_positions(self) -> List[Dict[str, Any]]:
        return self._positions

    async def get_orders(self) -> List[Dict[str, Any]]:
        return self._orders

    async def place_order(self, order_params: Dict[str, Any]) -> Dict[str, Any]:
        order_id = f"PAPER_ORD_{uuid.uuid4().hex[:8]}"
        timestamp = datetime.now(timezone.utc).isoformat()
        order = {
            "order_id": order_id,
            "status": "FILLED",  # Market orders in paper mode are instantly filled
            "side": order_params.get("transaction_type", "BUY"),
            "quantity": order_params.get("quantity", 0),
            "price": order_params.get("price", await self.get_ltp(order_params.get("instrument_token", ""))),
            "instrument_token": order_params.get("instrument_token", ""),
            "timestamp": timestamp,
            "params": order_params
        }
        self._orders.append(order)
        logger.info(f"[PAPER] Placed order: {order_id} - {order_params}")
        
        # In a very simple paper broker, we could update _positions here as well,
        # but since our app's database will track positions accurately via the TradeManager,
        # we'll keep the broker simple.
        
        return order

    async def modify_order(self, order_id: str, modify_params: Dict[str, Any]) -> Dict[str, Any]:
        logger.info(f"[PAPER] Modified order: {order_id}")
        return {"order_id": order_id, "status": "MODIFIED"}

    async def cancel_order(self, order_id: str) -> bool:
        logger.info(f"[PAPER] Cancelled order: {order_id}")
        return True

    async def exit_position(self, position_id: str) -> bool:
        logger.info(f"[PAPER] Exited position: {position_id}")
        return True

    async def get_order_status(self, order_id: str) -> str:
        return "FILLED"

    def reset(self):
        """Reset in-memory paper broker state (positions, orders, prices)."""
        self._positions.clear()
        self._orders.clear()
        self._injected_prices.clear()
        logger.info("[PAPER] In-memory paper broker state reset")

