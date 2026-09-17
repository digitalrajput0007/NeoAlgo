import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from app.brokers.execution_manager import ExecutionBroker
from app.config import settings

@pytest.fixture
def mock_paper_broker():
    broker = AsyncMock()
    broker.place_order.return_value = {"order_id": "PAPER_1", "status": "FILLED", "price": 100}
    return broker

@pytest.fixture
def mock_live_broker():
    broker = AsyncMock()
    broker.place_order.return_value = {"order_id": "LIVE_1", "status": "OPEN", "price": 100}
    return broker

@pytest.fixture
def execution_manager(mock_paper_broker, mock_live_broker):
    return ExecutionBroker(paper_broker=mock_paper_broker, live_broker=mock_live_broker)

@pytest.mark.asyncio
async def test_paper_mode_routes_to_paper_broker(execution_manager, mock_paper_broker, mock_live_broker):
    settings.neoalgo_mode = "PAPER"
    settings.live_trading_enabled = False
    
    await execution_manager.place_order({"price": 100})
    
    mock_paper_broker.place_order.assert_called_once()
    mock_live_broker.place_order.assert_not_called()

@pytest.mark.asyncio
async def test_live_mode_without_enable_flag_fails_closed(execution_manager, mock_paper_broker, mock_live_broker):
    settings.neoalgo_mode = "LIVE"
    settings.live_trading_enabled = False
    
    with pytest.raises(RuntimeError, match="LIVE_TRADING_ENABLED is not true"):
        await execution_manager.place_order({"price": 100})
        
    mock_paper_broker.place_order.assert_not_called()
    mock_live_broker.place_order.assert_not_called()

@pytest.mark.asyncio
async def test_live_mode_with_enable_flag_routes_to_live_broker(execution_manager, mock_paper_broker, mock_live_broker):
    settings.neoalgo_mode = "LIVE"
    settings.live_trading_enabled = True
    
    await execution_manager.place_order({"price": 100})
    
    mock_paper_broker.place_order.assert_not_called()
    mock_live_broker.place_order.assert_called_once()

@pytest.mark.asyncio
async def test_unknown_mode_fails_closed(execution_manager, mock_paper_broker, mock_live_broker):
    settings.neoalgo_mode = "UNKNOWN"
    settings.live_trading_enabled = True
    
    with pytest.raises(RuntimeError, match="Invalid NEOALGO_MODE"):
        await execution_manager.place_order({"price": 100})
        
    mock_paper_broker.place_order.assert_not_called()
    mock_live_broker.place_order.assert_not_called()
