import pytest
from unittest.mock import AsyncMock, MagicMock
from datetime import date
from decimal import Decimal

from app.trading.trade_manager import TradeManager
from app.brokers.paper import PaperBroker
from app.telegram.models import TradeSignal
from app.database.models import Trade, TradeState, Signal, TradingSettings, Position

@pytest.fixture
def mock_db():
    db = AsyncMock()
    db.add = MagicMock()
    # Basic mock setup for execute().scalar_one_or_none()
    return db

@pytest.fixture
def paper_broker():
    return PaperBroker(simulator_mode=True)

@pytest.fixture
def trade_manager(mock_db, paper_broker):
    return TradeManager(mock_db, paper_broker)

def create_mock_signal_data():
    return TradeSignal(
        underlying="NIFTY",
        strike=23500,
        option_type="CE",
        expiry=date(2026, 9, 15),
        entry_trigger=Decimal("150"),
        stop_loss=Decimal("144"),
        target=Decimal("170"),
        telegram_cmp=Decimal("147"),
        raw_text="Test"
    )

@pytest.mark.asyncio
async def test_scenario_1_valid_lifecycle(trade_manager, paper_broker, mock_db):
    """
    Scenario 1: Signal -> 149 (Wait) -> 151 (Entry) -> 170 (Target Exit)
    """
    # 1. New Signal -> WAITING_FOR_ENTRY
    signal_data = create_mock_signal_data()
    
    # Mock Risk Manager to allow
    trade_manager.risk_manager.check_new_trade_allowed = AsyncMock(return_value=(True, "OK"))
    
    trade = await trade_manager.process_new_signal(
        user_id=1, broker_account_id=1, signal_data=signal_data, message_id=1
    )
    assert trade.status == TradeState.WAITING_FOR_ENTRY
    
    # Mock DB select for evaluate_market_prices
    # We need to mock the result of the Trade and Signal fetch
    mock_trade = Trade(id=1, user_id=1, status=TradeState.WAITING_FOR_ENTRY, instrument_token="PAPER_NIFTY_23500.0_CE_2026-09-15T00:00:00", quantity=0)
    mock_signal = Signal(id=1, entry_trigger=150.0, target=170.0, stop_loss=144.0)
    
    mock_result = MagicMock()
    mock_result.scalars().all.return_value = [mock_trade]
    mock_result.scalar_one.return_value = mock_signal
    mock_db.execute.return_value = mock_result
    
    # 2. Inject 149 -> No entry
    paper_broker.inject_price(mock_trade.instrument_token, 149.0)
    affected = await trade_manager.evaluate_market_prices(mock_trade.instrument_token, 149.0)
    assert len(affected) == 0
    assert mock_trade.status == TradeState.WAITING_FOR_ENTRY
    
    # 3. Inject 151 -> Entry
    paper_broker.inject_price(mock_trade.instrument_token, 151.0)
    
    # For Position update
    mock_pos_result = MagicMock()
    mock_pos_result.scalar_one_or_none.return_value = None
    mock_db.execute.side_effect = [mock_result, mock_result, mock_pos_result]
    
    affected = await trade_manager.evaluate_market_prices(mock_trade.instrument_token, 151.0)
    assert len(affected) == 1
    assert affected[0]["new_state"] == TradeState.POSITION_OPEN.value
    assert mock_trade.status == TradeState.POSITION_OPEN
    assert mock_trade.quantity == 75
    
    # 4. Inject 170 -> Target Exit
    mock_trade.status = TradeState.POSITION_OPEN
    
    mock_pos = Position(id=1, quantity=75, average_price=151.0, is_open=True)
    mock_pos_result.scalar_one_or_none.return_value = mock_pos
    mock_db.execute.side_effect = [mock_result, mock_result, mock_pos_result]
    
    paper_broker.inject_price(mock_trade.instrument_token, 170.0)
    affected = await trade_manager.evaluate_market_prices(mock_trade.instrument_token, 170.0)
    assert len(affected) == 1
    assert mock_trade.status == TradeState.CLOSED
    assert mock_pos.quantity == 0
    assert mock_trade.realized_pnl == (170.0 - 151.0) * 75

@pytest.mark.asyncio
async def test_scenario_2_stop_loss(trade_manager, paper_broker, mock_db):
    """
    Scenario 2: 151 (Entry) -> 143 (Stop Loss)
    """
    mock_trade = Trade(id=1, user_id=1, status=TradeState.POSITION_OPEN, instrument_token="PAPER_NIFTY_23500.0_CE_2026-09-15T00:00:00", quantity=75)
    mock_signal = Signal(id=1, entry_trigger=150.0, target=170.0, stop_loss=144.0)
    mock_pos = Position(id=1, quantity=75, average_price=151.0, is_open=True)
    
    mock_result = MagicMock()
    mock_result.scalars().all.return_value = [mock_trade]
    mock_result.scalar_one.return_value = mock_signal
    mock_pos_result = MagicMock()
    mock_pos_result.scalar_one_or_none.return_value = mock_pos
    
    mock_db.execute.side_effect = [mock_result, mock_result, mock_pos_result]
    
    paper_broker.inject_price(mock_trade.instrument_token, 143.0)
    affected = await trade_manager.evaluate_market_prices(mock_trade.instrument_token, 143.0)
    
    assert len(affected) == 1
    assert mock_trade.status == TradeState.CLOSED
    assert mock_trade.realized_pnl == (143.0 - 151.0) * 75 # Loss

@pytest.mark.asyncio
async def test_scenario_9_daily_loss_exceeded(trade_manager, mock_db):
    """Scenario 9: Maximum daily loss exceeded."""
    trade_manager.risk_manager.check_new_trade_allowed = AsyncMock(return_value=(False, "MAX_DAILY_LOSS_EXCEEDED"))
    signal_data = create_mock_signal_data()
    
    trade = await trade_manager.process_new_signal(
        user_id=1, broker_account_id=1, signal_data=signal_data, message_id=1
    )
    
    assert trade.status == TradeState.REJECTED
