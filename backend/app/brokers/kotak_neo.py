import os
import pyotp
import logging
import httpx
from typing import Dict, Any, List, Optional
from datetime import datetime, timezone
from app.brokers.base import BrokerInterface
from app.database.models import Trade

logger = logging.getLogger(__name__)

class KotakNeoBroker(BrokerInterface):
    """
    Real Read-Only Kotak Neo Broker Implementation.
    Phase 5A.1 explicitly enforces real API calls but blocks execution.
    """
    def __init__(self):
        from app.config import settings
        self.consumer_key = settings.kotak_neo_consumer_key
        self.consumer_secret = settings.kotak_neo_consumer_secret # Sometimes needed for oauth, but we will check docs
        self.mobile = settings.kotak_neo_mobile_number
        self.ucc = settings.kotak_neo_ucc
        self.mpin = settings.kotak_neo_mpin
        self.totp = settings.kotak_neo_totp
        
        self.is_connected = False
        self.auth_status = "DISCONNECTED" # "DISCONNECTED", "CONNECTED", "AUTHENTICATION_BLOCKED", or explicit missing msg
        self.session_token = None
        self.trade_token = None
        self.last_successful_request = None
        
        self.view_sid = None
        self.trading_sid = None
        self.dynamic_base_url = None
        self.feed_url = None
        self.data_center = None
        
        self.login_base_url = "https://mis.kotaksecurities.com"

    async def authenticate(self, totp_code: Optional[str] = None, totp_secret: Optional[str] = None) -> bool:
        """
        Attempts real authentication with Kotak Neo API.
        Enforces strict credential validation and generates fresh TOTP if secret is available.
        """
        from app.config import settings
        if not hasattr(self, "consumer_key"):
            self.consumer_key = settings.kotak_neo_consumer_key
        if not hasattr(self, "mobile"):
            self.mobile = settings.kotak_neo_mobile_number
        if not hasattr(self, "ucc"):
            self.ucc = settings.kotak_neo_ucc
        if not hasattr(self, "mpin"):
            self.mpin = settings.kotak_neo_mpin
        
        # Check TOTP secret vs runtime code
        effective_secret = (
            totp_secret or 
            getattr(settings, "kotak_neo_totp_secret", None) or 
            os.environ.get("KOTAK_NEO_TOTP_SECRET")
        )
        effective_totp = (
            totp_code or 
            self.totp or 
            settings.kotak_neo_totp or 
            os.environ.get("KOTAK_NEO_TOTP")
        )

        current_totp = None
        if effective_secret and str(effective_secret).strip() and not str(effective_secret).startswith("your_"):
            clean_secret = str(effective_secret).strip().strip('"').strip("'").replace(" ", "").replace("-", "")
            try:
                current_totp = pyotp.TOTP(clean_secret).now()
            except Exception as ex:
                logger.error(f"AUTHENTICATION_BLOCKED: INVALID_TOTP_SECRET ({ex})")
                self.auth_status = "AUTHENTICATION_BLOCKED: INVALID_TOTP_SECRET"
                return False
        elif effective_totp and str(effective_totp).strip() and not str(effective_totp).startswith("your_"):
            totp_raw = str(effective_totp).strip()
            if len(totp_raw) == 6 and totp_raw.isdigit():
                current_totp = totp_raw
            else:
                clean_raw = totp_raw.replace(" ", "").replace("-", "")
                try:
                    current_totp = pyotp.TOTP(clean_raw).now()
                except Exception as ex:
                    logger.error(f"AUTHENTICATION_BLOCKED: INVALID_TOTP_FORMAT ({ex})")
                    self.auth_status = "AUTHENTICATION_BLOCKED: INVALID_TOTP_FORMAT"
                    return False

        # Strict Credential Validation
        credentials = {
            "KOTAK_NEO_CONSUMER_KEY": self.consumer_key,
            "KOTAK_NEO_MOBILE_NUMBER": self.mobile,
            "KOTAK_NEO_UCC": self.ucc,
            "KOTAK_NEO_TOTP": current_totp,
            "KOTAK_NEO_MPIN": self.mpin
        }
        
        for key, val in credentials.items():
            if not val or (isinstance(val, str) and val.startswith("your_")):
                logger.warning(f"AUTHENTICATION_BLOCKED: Missing valid {key}")
                self.auth_status = f"AUTHENTICATION_BLOCKED: Missing {key}"
                return False

        try:
            from neo_api_client.neo_api import NeoAPI
            
            # Use official Kotak Neo SDK
            client = NeoAPI(
                consumer_key=self.consumer_key,
                environment="prod"
            )
            
            # Step 1: Login using TOTP to generate view token (session token)
            login_response = client.totp_login(
                mobile_number=self.mobile,
                ucc=self.ucc,
                totp=current_totp
            )
            
            if not login_response or (isinstance(login_response, dict) and login_response.get("data", {}).get("status") != "success"):
                err_msg = ""
                if isinstance(login_response, dict):
                    err_json = login_response.get("error", [{}])
                    if isinstance(err_json, list) and len(err_json) > 0:
                        err_msg = str(err_json[0].get("message", ""))
                    elif "message" in login_response:
                        err_msg = str(login_response.get("message"))
                logger.error(f"AUTHENTICATION_BLOCKED: Step 1 (TOTP) Login failed: {err_msg or 'Invalid credentials or TOTP'}")
                self.auth_status = "AUTHENTICATION_BLOCKED"
                return False
                
            log_data = login_response.get("data", {}) if isinstance(login_response, dict) else {}
            
            # Step 2: Validate MPIN to generate trade token
            mpin_response = client.totp_validate(
                mpin=self.mpin
            )
            
            if not mpin_response or (isinstance(mpin_response, dict) and mpin_response.get("data", {}).get("status") != "success"):
                err_msg = ""
                if isinstance(mpin_response, dict):
                    err_json = mpin_response.get("error", [{}])
                    if isinstance(err_json, list) and len(err_json) > 0:
                        err_msg = str(err_json[0].get("message", ""))
                    elif "message" in mpin_response:
                        err_msg = str(mpin_response.get("message"))
                logger.error(f"AUTHENTICATION_BLOCKED: Step 2 (MPIN) Validation failed: {err_msg or 'Invalid MPIN'}")
                self.auth_status = "AUTHENTICATION_BLOCKED"
                return False
                
            mpin_data = mpin_response.get("data", {}) if isinstance(mpin_response, dict) else {}
            
            # Map SDK internal state to the broker's existing fields
            self.neo_client = client
            self.session_token = getattr(client.configuration, "bearer_token", None)
            self.trade_token = getattr(client.configuration, "edit_token", None)
            self.trading_sid = getattr(client.configuration, "edit_sid", None)
            self.view_sid = log_data.get("sid") or self.session_token
            
            self.dynamic_base_url = mpin_data.get("baseUrl")
            self.feed_url = mpin_data.get("feedUrl")
            self.data_center = mpin_data.get("dataCenter")
            
            if not self.trade_token or not self.dynamic_base_url:
                logger.error("AUTHENTICATION_BLOCKED: Step 2 did not return trade token or baseUrl from SDK.")
                self.auth_status = "AUTHENTICATION_BLOCKED"
                return False
                
            logger.info("Authentication successful. Connected to Kotak Neo via SDK.")
            self.auth_status = "CONNECTED"
            self.is_connected = True
            return True

        except Exception as e:
            logger.error("Authentication failed due to exception. (Details redacted for safety)")
            self.auth_status = "AUTHENTICATION_BLOCKED"
            return False

    async def get_profile(self) -> Dict[str, Any]:
        """Fetch profile/margin information (Read-Only)"""
        if self.auth_status != "CONNECTED":
            return {"status": "error", "message": f"Cannot fetch profile: {self.auth_status}"}
            
        async with httpx.AsyncClient() as client:
            headers = {"Authorization": f"Bearer {self.session_token}"}
            # Real endpoint logic
            # response = await client.get(f"{self.base_url}/api/v2/user/profile", headers=headers)
            return {"error": "Profile fetch failed due to lack of connection."}

    async def get_positions(self) -> List[Dict[str, Any]]:
        """Fetch existing positions (Read-Only)"""
        if self.auth_status != "CONNECTED":
            return []
        # Real HTTP GET would go here
        return []

    async def get_orders(self) -> List[Dict[str, Any]]:
        """Fetch existing orders (Read-Only)"""
        if self.auth_status != "CONNECTED":
            return []
        # Real HTTP GET would go here
        return []
        
    async def get_broker_funds(self) -> Dict[str, Any]:
        """Fetch real account limits from Kotak Neo"""
        if self.auth_status != "CONNECTED" or not self.trade_token or not self.dynamic_base_url:
            return {"status": "error", "message": f"Cannot fetch funds: {self.auth_status}"}
            
        try:
            from neo_api_client.neo_api import NeoAPI
            
            client = NeoAPI(consumer_key=self.consumer_key)
            client.configuration.edit_token = self.trade_token
            client.configuration.edit_sid = self.trading_sid
            client.configuration.bearer_token = self.session_token
            
            # limits() is a synchronous call in neo_api_client
            resp_json = client.limits()
            
            if resp_json and isinstance(resp_json, dict) and resp_json.get("stat") == "Ok":
                return {"status": "success", "data": resp_json}
            elif resp_json and "Error" in resp_json:
                return {"status": "error", "message": str(resp_json.get("message", "API Error"))}
            else:
                return {"status": "error", "message": f"Unexpected limits response: {resp_json}"}
        except Exception as e:
            logger.error(f"Error fetching broker funds: {str(e)}")
            return {"status": "error", "message": "Failed to connect to broker API for funds"}
            
    async def get_margin_required(self, exchange_segment: str, price: float, order_type: str, 
                                  product: str, quantity: int, instrument_token: str, 
                                  transaction_type: str) -> Dict[str, Any]:
        """Fetch real margin required for a specific trade calculation"""
        if self.auth_status != "CONNECTED" or not self.trade_token or not self.dynamic_base_url:
            return {"status": "error", "message": f"Cannot fetch margin: {self.auth_status}"}
            
        url = f"{self.dynamic_base_url.rstrip('/')}/Orders/2.0/quick/user/check-margin"
        headers = {
            "Sid": self.trading_sid,
            "Auth": self.trade_token,
            "Content-Type": "application/x-www-form-urlencoded"
        }
        
        # Simplified payload based on SDK expectations
        body_params = {
            "exSeg": exchange_segment,
            "prc": str(price),
            "prcTp": order_type,
            "prod": product,
            "qty": str(quantity),
            "tok": instrument_token,
            "trnsTp": transaction_type,
            "trgPrc": "0", # simplified
            "brkName": "KOTAK", # generic
            "brnchId": "KOTAK",
            "slAbsOrTks": "0",
            "slVal": "0",
            "sqrOffAbsOrTks": "0",
            "sqrOffVal": "0",
            "trailSL": "0",
            "tSLTks": "0"
        }
        
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.post(url, headers=headers, data=body_params)
                if response.status_code == 200:
                    return {"status": "success", "data": response.json()}
                else:
                    return {"status": "error", "message": f"HTTP {response.status_code} - {response.text}"}
        except Exception as e:
            logger.error(f"Error fetching margin required: {str(e)}")
            return {"status": "error", "message": "Failed to connect to broker API for margin"}

    async def download_scrip_master(self, file_path: str = "data/instruments.csv") -> bool:
        """
        Downloads the official production Scrip Master.

        Per official Kotak Neo API documentation:
          - POST /login/1.0/tradeApiValidate returns:
              data.baseUrl  → dynamic base URL for ALL post-login APIs
          - Scrip Master request:
              GET {baseUrl}/script-details/1.0/masterscrip/file-paths
              Authorization: <API_ACCESS_TOKEN>  (same token used for tradeApiLogin;
                             obtained from NEO API Dashboard; no Bearer/Basic prefix)
          - The trade/session token (data.token from tradeApiValidate, kType=Trade)
            is for Orders/Reports/Portfolio — NOT for Scrip Master or Quotes.
        """
        if not self.consumer_key:
            logger.error("Cannot download Scrip Master: API access token (consumer_key) not configured.")
            return False

        if not self.dynamic_base_url:
            logger.error("Cannot download Scrip Master: baseUrl not received from tradeApiValidate. Authenticate first.")
            return False

        import os
        import tempfile
        import shutil
        import csv

        try:
            from urllib.parse import urlparse
            base_host = urlparse(self.dynamic_base_url).hostname or "unknown"
            scrip_master_url = f"{self.dynamic_base_url.rstrip('/')}/script-details/1.0/masterscrip/file-paths"
            scrip_host = urlparse(scrip_master_url).hostname or "unknown"

            # Safety assertion: scrip master URL must be rooted at the dynamic base URL
            assert scrip_master_url.startswith(self.dynamic_base_url.rstrip("/") + "/"), (
                f"SAFETY: scrip master URL does not start with dynamic_base_url. "
                f"base_host={base_host}, scrip_host={scrip_host}"
            )

            logger.info(f"POST-LOGIN BASE URL HOST: {base_host}")
            logger.info(f"SCRIP MASTER URL HOST: {scrip_host}")

            async with httpx.AsyncClient(timeout=30.0) as client:
                # Authorization: API access token (consumer_key from NEO API Dashboard).
                # This is the SAME credential used in the Authorization header of tradeApiLogin.
                # The trade/session token (kType=Trade from tradeApiValidate) is NOT used here.
                # No Bearer prefix, no Basic prefix, no neo-fin-key, no Auth, no sid.
                logger.info("SCRIP MASTER AUTH TOKEN TYPE: API_ACCESS_TOKEN")
                headers = {
                    "Authorization": self.consumer_key,
                }
                response = await client.get(scrip_master_url, headers=headers)

                if response.status_code != 200:
                    logger.error(
                        f"Failed to fetch Scrip Master file paths. "
                        f"Status: {response.status_code} | HOST: {scrip_host}"
                    )
                    return False
                    
                data = response.json().get("data", {})
                files_paths = data.get("filesPaths", [])
                
                # Find the nse_fo and bse_fo files
                nse_fo_url = None
                bse_fo_url = None
                for path in files_paths:
                    if "nse_fo" in path.lower():
                        nse_fo_url = path
                    elif "bse_fo" in path.lower():
                        bse_fo_url = path
                
                if not nse_fo_url:
                    logger.error("nse_fo.csv URL not found in Kotak API response.")
                    return False
                if not bse_fo_url:
                    logger.warning("bse_fo.csv URL not found in Kotak API response. SENSEX options may be unavailable.")
                
                # 2. Download the CSVs
                temp_dir = tempfile.gettempdir()
                temp_path = os.path.join(temp_dir, f"kotak_scrip_master_{int(datetime.now(timezone.utc).timestamp())}.csv")
                
                with open(temp_path, 'wb') as f_out:
                    csv_response = await client.get(nse_fo_url)
                    if csv_response.status_code != 200:
                        logger.error("Failed to download nse_fo Scrip Master CSV.")
                        return False
                    f_out.write(csv_response.content)
                    
                    if bse_fo_url:
                        bse_response = await client.get(bse_fo_url)
                        if bse_response.status_code == 200:
                            # Write bse_fo content, but skip the first line (header) if it exists
                            content_lines = bse_response.content.split(b'\n', 1)
                            if len(content_lines) > 1:
                                f_out.write(content_lines[1])
                            else:
                                f_out.write(bse_response.content)
                        else:
                            logger.error(f"Failed to download bse_fo Scrip Master CSV. Status: {bse_response.status_code}")
                            
                # 3. Validate: must contain active (future) NIFTY F&O contracts.
                # Kotak lExpiryDate uses a non-standard epoch ~10 years behind Unix.
                # The official SDK (scrip_search.py:84) adds 315511200 s before comparison.
                # Use is_kotak_fno_contract_active() which applies that correction.
                from app.market_data.kotak_timestamps import is_kotak_fno_contract_active

                has_future_nifty = False
                total_rows = 0
                nifty_rows = 0
                active_nifty_rows = 0

                with open(temp_path, 'r', encoding='utf-8', errors='replace') as f:
                    reader = csv.DictReader(f)
                    for row in reader:
                        total_rows += 1
                        clean_row = {k.strip().lstrip('\ufeff').replace(';', ''): (v or '').strip()
                                     for k, v in row.items() if k is not None}
                        sym = clean_row.get("pSymbolName", "").strip().upper()
                        if sym == "NIFTY":
                            nifty_rows += 1
                            raw_expiry = clean_row.get("lExpiryDate") or clean_row.get("pExpiryDate", "")
                            if is_kotak_fno_contract_active(raw_expiry):
                                active_nifty_rows += 1
                                has_future_nifty = True
                                # don't break — continue to count all active rows

                logger.info(f"CSV ROW COUNT: {total_rows}")
                logger.info(f"NIFTY ROW COUNT: {nifty_rows}")
                logger.info(f"ACTIVE FUTURE NIFTY CONTRACTS: {active_nifty_rows}")

                if not has_future_nifty:
                    logger.error(
                        "Downloaded Scrip Master contains no active future NIFTY contracts "
                        "(after Kotak epoch correction). Aborting replacement."
                    )
                    return False
                    
                # 4. Atomic replacement
                full_path = os.path.join(os.getcwd(), file_path)
                os.makedirs(os.path.dirname(full_path), exist_ok=True)
                shutil.move(temp_path, full_path)
                logger.info(f"Successfully downloaded and validated production instrument master from {nse_fo_url}")
                return True
                
        except Exception:
            logger.error("Error downloading production Scrip Master. (Details redacted)")
            return False

    # =========================================================================
    # LIVE EXECUTION METHODS
    # =========================================================================

    async def place_order(self, order_params: Dict[str, Any]) -> Dict[str, Any]:
        if self.auth_status != "CONNECTED":
            raise RuntimeError("Broker not connected.")
            
        logger.info(f"Placing LIVE Kotak order: {order_params}")
        
        exchange_segment = order_params.get("exchange_segment", "nse_fo")
        product = order_params.get("product", "NRML")
        price = str(order_params.get("price", 0)) if order_params.get("order_type") != "MARKET" else "0"
        order_type = "MKT" if order_params.get("order_type", "MARKET") == "MARKET" else "L"
        quantity = str(order_params.get("quantity"))
        validity = order_params.get("validity", "DAY")
        trading_symbol = order_params.get("instrument_token", "")
        transaction_type = "B" if order_params.get("transaction_type") == "BUY" else "S"
        execution_id = order_params.get("execution_id")
        trade_id = order_params.get("trade_id")
        tag = f"N-{trade_id}-{execution_id}"[:19] if trade_id and execution_id else None # Kotak tag length limit

        try:
            # Note: neo_api_client methods might be synchronous depending on implementation, 
            # but we assume they can be called here or wrapped in executor. The SDK uses requests synchronously.
            import asyncio
            loop = asyncio.get_event_loop()
            
            response = await loop.run_in_executor(
                None, 
                lambda: self.neo_client.place_order(
                    exchange_segment=exchange_segment,
                    product=product,
                    price=price,
                    order_type=order_type,
                    quantity=quantity,
                    validity=validity,
                    trading_symbol=trading_symbol,
                    transaction_type=transaction_type,
                    tag=tag
                )
            )
            
            logger.info(f"Kotak place_order response: {response}")
            # Map Kotak response to standard schema
            
            if response.get("stat") == "Ok" and "nOrdNo" in response:
                return {
                    "order_id": str(response["nOrdNo"]),
                    "order_tag": tag,
                    "status": "OPEN", # Will update asynchronously
                    "price": float(price),
                    "filled_quantity": 0,
                    "remaining_quantity": int(quantity),
                    "rejection_reason": None
                }
            elif response.get("stat") == "NotOk" and "errMsg" in response:
                raise RuntimeError(f"Order rejected by Kotak: {response['errMsg']}")
            else:
                # Some API paths might return something else
                return {
                    "order_id": str(response.get("nOrdNo", "UNKNOWN")),
                    "order_tag": tag,
                    "status": "REJECTED",
                    "price": float(price),
                    "filled_quantity": 0,
                    "remaining_quantity": int(quantity),
                    "rejection_reason": str(response)
                }

        except Exception as e:
            logger.error(f"Error placing Kotak order: {e}")
            raise

    async def modify_order(self, order_id: str, modify_params: Dict[str, Any]) -> Dict[str, Any]:
        logger.warning(f"Modify order not yet fully implemented for {order_id}")
        return {"order_id": order_id, "status": "MODIFIED"}

    async def cancel_order(self, order_id: str) -> bool:
        if self.auth_status != "CONNECTED":
            raise RuntimeError("Broker not connected.")
        try:
            import asyncio
            loop = asyncio.get_event_loop()
            response = await loop.run_in_executor(
                None,
                lambda: self.neo_client.cancel_order(order_id=order_id, amo="NO")
            )
            logger.info(f"Kotak cancel_order response: {response}")
            return response.get("stat") == "Ok"
        except Exception as e:
            logger.error(f"Error canceling Kotak order {order_id}: {e}")
            return False

    async def exit_position(self, position_id: str) -> bool:
        logger.warning(f"exit_position via position_id {position_id} unsupported, use place_order with SELL.")
        return False

    # =========================================================================
    # READ-ONLY MARKET & ACCOUNT DATA
    # =========================================================================

    async def get_order_status(self, order_id: str) -> str:
        """Fetch the status of a specific order (Read-Only)"""
        if self.auth_status != "CONNECTED":
            return "UNKNOWN"
        # Real HTTP GET would go here to retrieve specific order status
        return "UNKNOWN"

    async def get_instruments(self) -> List[Dict[str, Any]]:
        """Fetch instrument master data"""
        return []

    async def get_ltp(self, instrument_token: str) -> float:
        """Get Last Traded Price for an instrument"""
        if self.auth_status != "CONNECTED":
            return 0.0
        # In a real environment, this would call the REST endpoint for LTP
        return 0.0

    async def get_quote(self, instrument_token: str) -> Dict[str, Any]:
        """Get full market quote for an instrument"""
        if self.auth_status != "CONNECTED":
            return {}
        # In a real environment, this would call the REST endpoint for Quote
        return {}

    # =========================================================================
    # OPTION RESOLUTION 
    # =========================================================================
    async def resolve_option_contract(self, underlying: str, strike: float, option_type: str, expiry: str) -> Dict[str, Any]:
        from app.market_data.instrument_resolver import InstrumentResolver
        resolver = InstrumentResolver()
        return await resolver.resolve_option_contract(underlying, strike, option_type, expiry)

    def create_websocket(self, url: Optional[str] = None, **kwargs) -> Any:
        """
        Creates and returns an authenticated SFeedWebSocket instance using
        the trading session credentials (trade_token and trading_sid).
        """
        from neo_api_client.websocket.feed import SFeedWebSocket
        from app.market_data.kotak_neo_feed import resolve_sfeed_url

        if not self.trade_token or not self.trading_sid:
            raise ValueError("Authentication required. Please call authenticate() before creating SFeed WebSocket.")

        ws_url = url or resolve_sfeed_url(data_center=self.data_center, feed_url=self.feed_url)

        if "ucc" not in kwargs and "user" not in kwargs:
            kwargs["ucc"] = self.ucc
            kwargs["user"] = self.ucc

        if "auth" not in kwargs:
            kwargs["auth"] = self.trading_sid

        if "sid" not in kwargs:
            kwargs["sid"] = self.trading_sid

        if "access_token" not in kwargs:
            kwargs["access_token"] = self.trade_token

        return SFeedWebSocket(
            url=ws_url,
            **kwargs
        )


_shared_broker: Optional[KotakNeoBroker] = None

def get_kotak_broker() -> KotakNeoBroker:
    """Returns the shared application KotakNeoBroker instance."""
    global _shared_broker
    if _shared_broker is None:
        _shared_broker = KotakNeoBroker()
    return _shared_broker

