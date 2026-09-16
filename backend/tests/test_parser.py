import pytest
from datetime import date
from decimal import Decimal
from app.telegram.models import TelegramMessageType, TradeSignal
from app.telegram.parser import parse_message

def test_valid_new_signal_1():
    text = "NIFTY 23300 PE 15 Sept 26 Expiry\nBuy above 36\nSL below 30\nTgt above 43\nCMP 35"
    result = parse_message(text)
    assert result.message_type == TelegramMessageType.NEW_SIGNAL
    assert result.parsed_successfully is True
    signal = result.signal
    assert signal.underlying == "NIFTY"
    assert signal.strike == 23300
    assert signal.option_type == "PE"
    assert signal.expiry == date(2026, 9, 15)
    assert signal.entry_trigger == Decimal("36")
    assert signal.stop_loss == Decimal("30")
    assert signal.target == Decimal("43")
    assert signal.telegram_cmp == Decimal("35")

def test_valid_new_signal_2():
    text = "NIFTY 23500 CE 08 Sept 26 Expiry\nBuy above 147\nSL below 140\nTgt above 170\nCMP 145"
    result = parse_message(text)
    assert result.message_type == TelegramMessageType.NEW_SIGNAL
    assert result.parsed_successfully is True
    assert result.signal.option_type == "CE"
    assert result.signal.expiry == date(2026, 9, 8)

def test_price_update():
    text = "From 36 to 58"
    result = parse_message(text)
    assert result.message_type == TelegramMessageType.PRICE_UPDATE
    assert result.parsed_successfully is True
    assert result.price_update.from_price == Decimal("36")
    assert result.price_update.to_price == Decimal("58")
    assert result.signal is None

def test_partial_profit():
    text = "Book Partial Profit and keep Trailing stop"
    result = parse_message(text)
    assert result.message_type == TelegramMessageType.PARTIAL_PROFIT
    assert result.parsed_successfully is True

def test_exit_signal():
    text = "Exit"
    result = parse_message(text)
    assert result.message_type == TelegramMessageType.EXIT
    assert result.parsed_successfully is True
    
def test_stop_loss():
    text = "SL hit"
    result = parse_message(text)
    assert result.message_type == TelegramMessageType.STOP_LOSS
    assert result.parsed_successfully is True

def test_informational_messages():
    texts = [
        "At 11:33 AM - Signal given",
        "Watch Youtube LIVE to Learn LOGIC behind Signal",
        "https://youtu.be/XYZ123",
        "General commentary on the market"
    ]
    for text in texts:
        result = parse_message(text)
        assert result.message_type in [TelegramMessageType.INFORMATIONAL, TelegramMessageType.UNKNOWN], f"Failed for {text}"

def test_invalid_ce_logic():
    # Stop loss higher than entry trigger for a CE
    text = "NIFTY 23500 CE 15 Sept 26 Expiry\nBuy above 150\nSL below 160\nTgt above 170\nCMP 150"
    result = parse_message(text)
    assert result.message_type == TelegramMessageType.NEW_SIGNAL
    assert result.parsed_successfully is False
    assert any("stop loss must be below entry trigger" in e for e in result.validation_errors)

def test_invalid_pe_logic():
    # Target lower than entry trigger for a PE
    text = "NIFTY 23500 PE 15 Sept 26 Expiry\nBuy above 100\nSL below 90\nTgt above 80\nCMP 100"
    result = parse_message(text)
    assert result.message_type == TelegramMessageType.NEW_SIGNAL
    assert result.parsed_successfully is False
    assert any("target must be above entry trigger" in e for e in result.validation_errors)

def test_missing_fields():
    text = "NIFTY 23500 CE 15 Sept 26 Expiry\nBuy above 150\nTgt above 170"
    result = parse_message(text)
    # Classifies as informational or unknown because it lacks 'sl below'
    assert result.message_type != TelegramMessageType.NEW_SIGNAL
