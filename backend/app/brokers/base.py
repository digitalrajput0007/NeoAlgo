from abc import ABC, abstractmethod
from typing import Any, Dict, List

class BrokerInterface(ABC):
    @abstractmethod
    async def authenticate(self) -> bool:
        pass

    @abstractmethod
    async def get_profile(self) -> Dict[str, Any]:
        pass

    @abstractmethod
    async def get_instruments(self) -> List[Dict[str, Any]]:
        pass

    @abstractmethod
    async def resolve_option_contract(self, underlying: str, strike: float, option_type: str, expiry: str) -> Dict[str, Any]:
        pass

    @abstractmethod
    async def get_ltp(self, instrument_token: str) -> float:
        pass

    @abstractmethod
    async def get_quote(self, instrument_token: str) -> Dict[str, Any]:
        pass

    @abstractmethod
    async def get_positions(self) -> List[Dict[str, Any]]:
        pass

    @abstractmethod
    async def get_orders(self) -> List[Dict[str, Any]]:
        pass

    @abstractmethod
    async def place_order(self, order_params: Dict[str, Any]) -> Dict[str, Any]:
        pass

    @abstractmethod
    async def modify_order(self, order_id: str, modify_params: Dict[str, Any]) -> Dict[str, Any]:
        pass

    @abstractmethod
    async def cancel_order(self, order_id: str) -> bool:
        pass

    @abstractmethod
    async def exit_position(self, position_id: str) -> bool:
        pass

    @abstractmethod
    async def get_order_status(self, order_id: str) -> str:
        pass
