import logging
from typing import Any, Dict, List
from app.config import settings
from app.brokers.base import BrokerInterface

logger = logging.getLogger(__name__)

class ExecutionBroker(BrokerInterface):
    """
    Execution proxy that enforces the NEOALGO_MODE and LIVE_TRADING_ENABLED safety gates.
    Routes execution to either PaperBroker or KotakNeoBroker based on the mode.
    """
    def __init__(self, paper_broker: BrokerInterface, live_broker: BrokerInterface):
        self.paper_broker = paper_broker
        self.live_broker = live_broker

    def _get_active_broker(self) -> BrokerInterface:
        mode = settings.neoalgo_mode.upper()
        if mode == "PAPER":
            return self.paper_broker
        elif mode == "LIVE":
            if not getattr(settings, "live_trading_enabled", False):
                logger.critical("LIVE mode requested, but LIVE_TRADING_ENABLED is False or missing. Failing closed.")
                raise RuntimeError("LIVE_TRADING_ENABLED is not true. Execution blocked for safety.")
            return self.live_broker
        else:
            logger.critical(f"Unknown NEOALGO_MODE: {mode}. Failing closed.")
            raise RuntimeError(f"Invalid NEOALGO_MODE: {mode}. Execution blocked for safety.")

    async def authenticate(self) -> bool:
        return await self._get_active_broker().authenticate()

    async def get_profile(self) -> Dict[str, Any]:
        return await self._get_active_broker().get_profile()

    async def get_instruments(self) -> List[Dict[str, Any]]:
        return await self._get_active_broker().get_instruments()

    async def resolve_option_contract(self, underlying: str, strike: float, option_type: str, expiry: str) -> Dict[str, Any]:
        return await self._get_active_broker().resolve_option_contract(underlying, strike, option_type, expiry)

    async def get_ltp(self, instrument_token: str) -> float:
        return await self._get_active_broker().get_ltp(instrument_token)

    async def get_quote(self, instrument_token: str) -> Dict[str, Any]:
        return await self._get_active_broker().get_quote(instrument_token)

    async def get_positions(self) -> List[Dict[str, Any]]:
        return await self._get_active_broker().get_positions()

    async def get_orders(self) -> List[Dict[str, Any]]:
        return await self._get_active_broker().get_orders()

    async def place_order(self, order_params: Dict[str, Any]) -> Dict[str, Any]:
        broker = self._get_active_broker()
        logger.info(f"[{settings.neoalgo_mode}] Dispatching place_order to {broker.__class__.__name__}")
        return await broker.place_order(order_params)

    async def modify_order(self, order_id: str, modify_params: Dict[str, Any]) -> Dict[str, Any]:
        broker = self._get_active_broker()
        return await broker.modify_order(order_id, modify_params)

    async def cancel_order(self, order_id: str) -> bool:
        broker = self._get_active_broker()
        return await broker.cancel_order(order_id)

    async def exit_position(self, position_id: str) -> bool:
        broker = self._get_active_broker()
        return await broker.exit_position(position_id)

    async def get_order_status(self, order_id: str) -> str:
        broker = self._get_active_broker()
        return await broker.get_order_status(order_id)
