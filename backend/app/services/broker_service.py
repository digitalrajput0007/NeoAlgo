import logging
import time
from typing import Dict, Any, Optional
from datetime import datetime, timezone
from app.brokers.kotak_neo import get_kotak_broker

logger = logging.getLogger(__name__)

class BrokerService:
    def __init__(self):
        self._cached_funds: Optional[Dict[str, Any]] = None
        self._last_funds_fetch_time: float = 0.0
        self.CACHE_TTL_SECONDS = 60.0

    async def get_cached_broker_funds(self, force_refresh: bool = False) -> Dict[str, Any]:
        """
        Returns cached broker funds to avoid spamming the Kotak API.
        Optionally force refresh.
        """
        current_time = time.time()
        
        # Return cache if valid and not forced
        if not force_refresh and self._cached_funds and (current_time - self._last_funds_fetch_time) < self.CACHE_TTL_SECONDS:
            return self._cached_funds
            
        broker = get_kotak_broker()
        response = await broker.get_broker_funds()
        
        if response.get("status") == "success":
            data = response.get("data", {})
            # We normalize it here for our app UI based on Kotak v3.0.6 Limits response schema
            normalized_funds = {
                "available_margin": None,
                "used_margin": None,
                "cash": None,
                "collateral": None,
                "rms_pay_in": None,
                "broker_fields": data,
                "last_updated": datetime.now(timezone.utc).isoformat()
            }
            
            try:
                if isinstance(data, dict):
                    if "Net" in data:
                        normalized_funds["available_margin"] = float(data["Net"] or 0.0)
                    if "MarginUsed" in data:
                        normalized_funds["used_margin"] = float(data["MarginUsed"] or 0.0)
                    if "Collateral" in data:
                        normalized_funds["collateral"] = float(data["Collateral"] or 0.0)
                    if "RmsPayInAmt" in data:
                        normalized_funds["rms_pay_in"] = float(data["RmsPayInAmt"] or 0.0)
            except Exception as e:
                logger.error(f"Error parsing broker funds response: {e}")
                
            self._cached_funds = normalized_funds
            self._last_funds_fetch_time = current_time
            return self._cached_funds
            
        else:
            logger.warning(f"Failed to fetch broker funds: {response.get('message')}")
            # If fetch fails, return the stale cache if we have one, otherwise return an error state
            if self._cached_funds:
                return self._cached_funds
            return {
                "error": True,
                "message": response.get("message", "Unknown error fetching broker funds"),
                "available_margin": None,
                "used_margin": None,
                "cash": None,
                "collateral": None,
                "rms_pay_in": None,
                "last_updated": datetime.now(timezone.utc).isoformat()
            }

broker_service = BrokerService()
