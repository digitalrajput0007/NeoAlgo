import pytest
from unittest.mock import patch, MagicMock
from app.services.broker_service import BrokerService
from app.brokers.kotak_neo import KotakNeoBroker
from typing import Dict, Any

@pytest.fixture
def broker_service():
    service = BrokerService()
    # Reset internal cache
    service._cached_funds = None
    service._last_funds_fetch_time = 0
    return service

@pytest.fixture
def mock_kotak_broker():
    broker = KotakNeoBroker()
    broker.auth_status = "CONNECTED"
    broker.trade_token = "fake_trade_token"
    broker.trading_sid = "fake_sid"
    broker.session_token = "fake_session_token"
    broker.dynamic_base_url = "https://fake"
    return broker

@pytest.mark.asyncio
async def test_get_cached_broker_funds_success(broker_service, mock_kotak_broker):
    mock_limits_response = {
        "stat": "Ok",
        "Net": "3154",
        "MarginUsed": "6846",
        "Collateral": "0",
        "RmsPayInAmt": "10000"
    }

    with patch('app.services.broker_service.get_kotak_broker', return_value=mock_kotak_broker):
        with patch('neo_api_client.neo_api.NeoAPI') as MockNeoAPI:
            # Setup mock NeoAPI client
            mock_client_instance = MagicMock()
            mock_client_instance.limits.return_value = mock_limits_response
            MockNeoAPI.return_value = mock_client_instance

            # Call service
            funds = await broker_service.get_cached_broker_funds(force_refresh=True)

            assert funds["available_margin"] == 3154.0
            assert funds["used_margin"] == 6846.0
            assert funds["collateral"] == 0.0
            assert funds["rms_pay_in"] == 10000.0
            assert funds["cash"] is None
            assert "broker_fields" in funds
            assert funds["broker_fields"]["Net"] == "3154"

@pytest.mark.asyncio
async def test_get_cached_broker_funds_api_error(broker_service, mock_kotak_broker):
    mock_limits_response = {
        "Error": "Some Error",
        "message": "Exchange Segment is not available"
    }

    with patch('app.services.broker_service.get_kotak_broker', return_value=mock_kotak_broker):
        with patch('neo_api_client.neo_api.NeoAPI') as MockNeoAPI:
            # Setup mock NeoAPI client
            mock_client_instance = MagicMock()
            mock_client_instance.limits.return_value = mock_limits_response
            MockNeoAPI.return_value = mock_client_instance

            # Call service
            funds = await broker_service.get_cached_broker_funds(force_refresh=True)

            assert funds["error"] is True
            assert funds["message"] == "Exchange Segment is not available"
            assert funds["available_margin"] is None
            assert funds["cash"] is None
