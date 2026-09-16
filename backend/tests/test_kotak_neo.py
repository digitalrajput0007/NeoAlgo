import pytest
from app.brokers.kotak_neo import KotakNeoBroker
from app.market_data.instrument_resolver import InstrumentResolver

@pytest.fixture
def kotak_broker():
    broker = KotakNeoBroker()
    broker.consumer_key = "test_consumer_key"
    broker.mobile = "1234567890"
    broker.ucc = "TESTUCC"
    broker.mpin = "123456"
    # Valid 6-digit TOTP
    broker.totp = "123456"
    return broker

@pytest.mark.asyncio
async def test_authentication_failure():
    broker = KotakNeoBroker()
    # Missing credentials should yield AUTHENTICATION_BLOCKED
    broker.consumer_key = None
    success = await broker.authenticate()
    assert success is False
    assert broker.is_connected is False
    assert "AUTHENTICATION_BLOCKED" in broker.auth_status

@pytest.mark.asyncio
async def test_profile_retrieval(kotak_broker):
    await kotak_broker.authenticate()
    profile = await kotak_broker.get_profile()
    # In mock / disconnected mode, it should not crash but return error
    assert "error" in profile or "Cannot fetch profile" in profile.get("message", "")

@pytest.mark.asyncio
async def test_blocked_execution(kotak_broker):
    await kotak_broker.authenticate()
    
    with pytest.raises(NotImplementedError) as exc:
        await kotak_broker.place_order({})
    assert "Live order execution is disabled" in str(exc.value)

    with pytest.raises(NotImplementedError):
        await kotak_broker.modify_order("123", {})

    with pytest.raises(NotImplementedError):
        await kotak_broker.cancel_order("123")

    with pytest.raises(NotImplementedError):
        await kotak_broker.exit_position("123")

@pytest.mark.asyncio
async def test_read_only_methods(kotak_broker):
    # Tests that abstract compliance methods can be called safely without crashing
    assert await kotak_broker.get_order_status("123") == "UNKNOWN"
    assert await kotak_broker.get_instruments() == []
    assert await kotak_broker.get_ltp("token") == 0.0
    assert await kotak_broker.get_quote("token") == {}

import httpx
from unittest.mock import patch, MagicMock

@pytest.mark.asyncio
async def test_successful_authentication_flow(kotak_broker, caplog):
    """
    Tests:
    1. Successful TOTP generation
    2. TOTP login request has the correct endpoint
    3. TOTP login has Authorization: consumer_key (not Basic)
    4. TOTP login has neo-fin-key: neotradeapi
    5. Payload contains mobileNumber, ucc, and totp
    6. VIEW_TOKEN and VIEW_SID are extracted correctly
    7. MPIN validation uses VIEW_TOKEN + VIEW_SID
    8. TRADING_TOKEN, TRADING_SID, dynamic BASE_URL are extracted
    12. Secrets/tokens are never present in logs
    """
    import logging
    caplog.set_level(logging.DEBUG)
    
    class MockResponse:
        def __init__(self, status_code, json_data, content=b""):
            self.status_code = status_code
            self._json_data = json_data
            self.content = content
            
        def json(self):
            return self._json_data

    call_args_list = []
    
    async def mock_post(url, headers=None, json=None, data=None):
        call_args_list.append({"url": url, "headers": headers, "json": json, "data": data})
        if "tradeApiLogin" in url:
            return MockResponse(200, {"data": {"token": "mock_view_token", "sid": "mock_view_sid"}})
        elif "tradeApiValidate" in url:
            return MockResponse(200, {"data": {"token": "mock_trade_token", "sid": "mock_trade_sid", "baseUrl": "https://mock.base.url"}})
        return MockResponse(404, {})

    with patch("httpx.AsyncClient.post", side_effect=mock_post):
        success = await kotak_broker.authenticate()
        
    assert success is True
    assert len(call_args_list) == 2
    
    login_call = call_args_list[0]
    assert login_call["url"] == "https://mis.kotaksecurities.com/login/1.0/tradeApiLogin"
    assert login_call["headers"]["Authorization"] == "test_consumer_key"
    assert "Basic" not in login_call["headers"]["Authorization"]
    assert login_call["headers"]["neo-fin-key"] == "neotradeapi"
    assert "mobileNumber" in login_call["json"]
    assert "ucc" in login_call["json"]
    assert "totp" in login_call["json"]
    # Verify TOTP is a 6 digit code (generated from Base32)
    assert len(login_call["json"]["totp"]) == 6
    assert login_call["json"]["totp"].isdigit()
    
    validate_call = call_args_list[1]
    assert validate_call["url"] == "https://mis.kotaksecurities.com/login/1.0/tradeApiValidate"
    assert validate_call["headers"]["sid"] == "mock_view_sid"
    assert validate_call["headers"]["Auth"] == "mock_view_token"
    assert "mpin" in validate_call["json"]
    
    assert kotak_broker.session_token == "mock_view_token"
    assert kotak_broker.trade_token == "mock_trade_token"
    assert kotak_broker.dynamic_base_url == "https://mock.base.url"
    
    # 12. Ensure secrets not in logs
    log_text = caplog.text
    assert "test_consumer_key" not in log_text
    assert "mock_view_token" not in log_text
    assert "JBSWY3DPEHPK3PXP" not in log_text
    assert "123456" not in log_text

@pytest.mark.asyncio
async def test_authentication_failed_sanitized(kotak_broker, caplog):
    """13. Failed authentication produces a sanitized error."""
    class MockResponse:
        def __init__(self, status_code):
            self.status_code = status_code
        def json(self):
            return {}

    async def mock_post_fail(url, **kwargs):
        # Return 401 Unauthorized for login
        return MockResponse(401)
        
    with patch("httpx.AsyncClient.post", side_effect=mock_post_fail):
        success = await kotak_broker.authenticate()
        
    assert success is False
    assert "AUTHENTICATION_BLOCKED: Step 1 (TOTP) Login failed" in caplog.text
    # Should not print the actual exception text or anything from the HTTP response natively
    assert kotak_broker.auth_status == "AUTHENTICATION_BLOCKED"

@pytest.mark.asyncio
async def test_scrip_master_download(kotak_broker):
    """
    9. Scrip Master uses dynamic BASE_URL (from tradeApiValidate) as host.
    10. Authorization uses the API access token (consumer_key / NEO dashboard token),
        NOT the trade/session token returned by tradeApiValidate.
    11. Old hardcoded mis.kotaksecurities.com / gw-napi is NOT used.
    12. Historical/stale instrument master is rejected.
    Per official API doc:
        GET {baseUrl}/script-details/1.0/masterscrip/file-paths
        Authorization: <API_ACCESS_TOKEN>  (same credential as tradeApiLogin; no prefix)
    """
    kotak_broker.auth_status = "CONNECTED"
    kotak_broker.trade_token = "test_trade_token"
    kotak_broker.dynamic_base_url = "https://mock.base.url"
    
    class MockResponse:
        def __init__(self, status_code, json_data={}, content=b""):
            self.status_code = status_code
            self._json_data = json_data
            self.content = content
        def json(self):
            return self._json_data

    call_args_list = []
    
    async def mock_get(url, headers=None, **kwargs):
        call_args_list.append({"url": url, "headers": headers})
        if "file-paths" in url:
            return MockResponse(200, {"data": {"filesPaths": ["https://csv.url/nse_fo.csv"]}})
        elif "nse_fo.csv" in url:
            # Dummy CSV that does NOT have any future NIFTY options (historical/stale)
            content = b"pSymbolName,pOptionType,pExpiryDate,pTrdSymbol\nNIFTY,CE,1472774400,TEST_SYM"
            return MockResponse(200, {}, content=content)
        return MockResponse(404)
        
    with patch("httpx.AsyncClient.get", side_effect=mock_get):
        success = await kotak_broker.download_scrip_master("dummy_out.csv")
        
    assert success is False  # Rejected because stale CSV has no future NIFTY contracts
    assert len(call_args_list) == 2
    
    # Assert correct URL: must use dynamic_base_url, NOT mis.kotaksecurities.com / gw-napi
    assert call_args_list[0]["url"] == "https://mock.base.url/script-details/1.0/masterscrip/file-paths"
    assert "mis.kotaksecurities.com" not in call_args_list[0]["url"]
    assert "gw-napi" not in call_args_list[0]["url"]
    
    # Assert correct Authorization: consumer_key (API access token), no prefix, no trade_token, no neo-fin-key
    assert call_args_list[0]["headers"]["Authorization"] == "test_consumer_key"
    assert "Bearer" not in call_args_list[0]["headers"]["Authorization"]
    assert "Basic" not in call_args_list[0]["headers"]["Authorization"]
    assert "test_trade_token" not in str(call_args_list[0]["headers"])  # trade token must NOT be used
    assert "neo-fin-key" not in call_args_list[0]["headers"]
    assert call_args_list[1]["url"] == "https://csv.url/nse_fo.csv"

@pytest.mark.asyncio
async def test_instrument_resolver_nearest_expiry(monkeypatch):
    from app.market_data.instrument_resolver import InstrumentResolver
    from app.market_data.kotak_timestamps import KOTAK_FNO_EPOCH_OFFSET_SECONDS
    resolver = InstrumentResolver("dummy_test.csv")
    # Mock cache directly to avoid needing a real CSV for this test.
    # Kotak CSV timestamps (lExpiryDate / pExpiryDate) are in Kotak epoch
    # (approximately 10 years behind standard Unix epoch).
    import time
    now = time.time()
    kotak_now = now - KOTAK_FNO_EPOCH_OFFSET_SECONDS
    old_ts = str(int(kotak_now - 86400))
    nearest_ts = str(int(kotak_now + 86400 * 3))
    far_ts = str(int(kotak_now + 86400 * 10))

    resolver._cache = [
        {"pSymbolName": "NIFTY", "pSymbol": "OLD_TOKEN", "pStrikePrice": "24000", "pOptionType": "CE", "pExpiryDate": old_ts, "lExpiryDate": old_ts, "pTrdSymbol": "OLD_SYM"},
        {"pSymbolName": "NIFTY", "pSymbol": "NEAREST_TOKEN", "pStrikePrice": "24000", "pOptionType": "CE", "pExpiryDate": nearest_ts, "lExpiryDate": nearest_ts, "pTrdSymbol": "NEAREST_SYM"},
        {"pSymbolName": "NIFTY", "pSymbol": "FAR_TOKEN", "pStrikePrice": "24000", "pOptionType": "CE", "pExpiryDate": far_ts, "lExpiryDate": far_ts, "pTrdSymbol": "FAR_SYM"},
    ]
    
    # 1. explicit future expiry resolved exactly
    res1 = await resolver.resolve_option_contract("NIFTY", 24000, "CE", expiry=far_ts)
    assert res1["instrument_token"] == "FAR_TOKEN"
    assert res1["selection_mode"] == "EXPLICIT_EXPIRY"
    
    # 2. missing expiry selects nearest future weekly expiry (skips past expiry)
    res2 = await resolver.resolve_option_contract("NIFTY", 24000, "CE")
    assert res2["instrument_token"] == "NEAREST_TOKEN"
    assert res2["selection_mode"] == "AUTO_SELECTED_NEAREST_WEEKLY_EXPIRY"
    
    # 3. expired explicit expiry rejected
    with pytest.raises(ValueError) as exc:
        await resolver.resolve_option_contract("NIFTY", 24000, "CE", expiry=old_ts)
    assert "INSTRUMENT_EXPIRED" in str(exc.value)
    
    # 4. no future weekly expiry returns INSTRUMENT_NOT_FOUND
    resolver._cache = [
        {"pSymbolName": "NIFTY", "pSymbol": "OLD_TOKEN", "pStrikePrice": "25000", "pOptionType": "PE", "pExpiryDate": old_ts, "lExpiryDate": old_ts, "pTrdSymbol": "OLD_TOKEN"}
    ]
    with pytest.raises(ValueError) as exc:
        await resolver.resolve_option_contract("NIFTY", 25000, "PE")
    assert "INSTRUMENT_NOT_FOUND" in str(exc.value)

@pytest.mark.asyncio
async def test_auth_failure_prevents_stale_resolution(kotak_broker):
    """
    If authentication fails, download_scrip_master() skips the download.
    If a stale 2016 CSV exists locally, InstrumentResolver might load it,
    but it must strictly reject it during resolution because there are no
    valid future NIFTY contracts.
    """
    # 1. Force auth failure
    kotak_broker.consumer_key = None
    auth_success = await kotak_broker.authenticate()
    assert auth_success is False
    
    # 2. Attempt download, which should safely abort
    download_success = await kotak_broker.download_scrip_master("dummy_stale.csv")
    assert download_success is False
    
    # 3. Simulate resolver loading a stale 2016 CSV (like the WSO2 one)
    from app.market_data.instrument_resolver import InstrumentResolver
    resolver = InstrumentResolver("dummy_stale.csv")
    import time
    now = time.time()
    # 2016 expiry date
    resolver._cache = [
        {
            "pSymbolName": "NIFTY", 
            "pSymbol": "STALE_TOKEN", 
            "pStrikePrice": "25000", 
            "pOptionType": "CE", 
            "pExpiryDate": "1472774400", # 2016 timestamp
            "lExpiryDate": "1472774400",
            "pTrdSymbol": "STALE_SYM"
        }
    ]
    
    # 4. Attempt to resolve NIFTY contract
    with pytest.raises(ValueError) as exc:
        await resolver.resolve_option_contract("NIFTY", 25000, "CE")
        
    assert "INSTRUMENT_NOT_FOUND" in str(exc.value)


@pytest.mark.asyncio
async def test_authentication_error_logging_sanitized(kotak_broker, caplog):
    """Verify that HTTP status and sanitized error payload from Kotak are logged without secret leakage."""
    import logging
    caplog.set_level(logging.DEBUG)

    class MockResponse:
        def __init__(self, status_code, json_data):
            self.status_code = status_code
            self._json_data = json_data
        def json(self):
            return self._json_data

    # 1. Step 1 returns 424 with error code 10508
    async def mock_step1_fail(url, **kwargs):
        if "tradeApiLogin" in url:
            return MockResponse(424, {"error": [{"code": "10508", "message": "TOTP not registered for this user."}]})
        return MockResponse(200, {})

    with patch("httpx.AsyncClient.post", side_effect=mock_step1_fail):
        success = await kotak_broker.authenticate()

    assert success is False
    assert "HTTP 424" in caplog.text
    assert "TOTP not registered for this user" in caplog.text
    assert "AUTHENTICATION_BLOCKED" in kotak_broker.auth_status

    # 2. Step 2 returns 400 with error payload
    caplog.clear()
    async def mock_step2_fail(url, **kwargs):
        if "tradeApiLogin" in url:
            return MockResponse(200, {"data": {"token": "mock_view_token", "sid": "mock_view_sid"}})
        if "tradeApiValidate" in url:
            return MockResponse(400, {"error": [{"code": "10509", "message": "Invalid MPIN."}]})
        return MockResponse(404, {})

    with patch("httpx.AsyncClient.post", side_effect=mock_step2_fail):
        success = await kotak_broker.authenticate()

    assert success is False
    assert "HTTP 400" in caplog.text
    assert "Invalid MPIN" in caplog.text
    assert "AUTHENTICATION_BLOCKED" in kotak_broker.auth_status

