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
            data = response.get("data", [])
            # Kotak typically returns a list of limits or a dict. 
            # We'll normalize it here for our app UI.
            
            # Find the core margin object (often type 'ALL' or similar if it's a list)
            normalized_funds = {
                "available_margin": 0.0,
                "used_margin": 0.0,
                "available_cash": 0.0,
                "raw_data": data,
                "updated_at": datetime.now(timezone.utc).isoformat()
            }
            
            try:
                # If it's a list of dictionaries (standard for Kotak limits)
                if isinstance(data, list):
                    for item in data:
                        if isinstance(item, dict):
                            normalized_funds["available_margin"] += float(item.get("Net", 0.0) or item.get("marginAvailable", 0.0) or 0.0)
                            normalized_funds["used_margin"] += float(item.get("MarginUsed", 0.0) or item.get("marginUsed", 0.0) or 0.0)
                            normalized_funds["available_cash"] += float(item.get("CollateralValue", 0.0) or item.get("cashAvailable", 0.0) or 0.0)
                elif isinstance(data, dict):
                    # In case it's a direct dictionary
                    normalized_funds["available_margin"] = float(data.get("Net", 0.0) or data.get("marginAvailable", 0.0) or 0.0)
                    normalized_funds["used_margin"] = float(data.get("MarginUsed", 0.0) or data.get("marginUsed", 0.0) or 0.0)
                    normalized_funds["available_cash"] = float(data.get("CollateralValue", 0.0) or data.get("cashAvailable", 0.0) or 0.0)
            except Exception as e:
                logger.error(f"Error parsing broker funds response: {e}")
                # We will still cache the raw data and whatever we got
                
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
                "available_margin": 0.0,
                "used_margin": 0.0,
                "available_cash": 0.0,
                "updated_at": datetime.now(timezone.utc).isoformat()
            }

broker_service = BrokerService()
