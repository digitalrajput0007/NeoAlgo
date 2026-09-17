import pytest
from app.telegram.parser import parse_message
from app.telegram.models import TelegramMessageType

def test_parser_nifty_ce():
    text = "NIFTY 23500 CE 15 Sept 26 Expiry\nBuy above 150\nSL below 144\nTgt above 170\nCMP 150"
    res = parse_message(text)
    assert res.parsed_successfully
    assert res.signal.underlying == "NIFTY"
    assert res.signal.strike == 23500
    assert res.signal.option_type == "CE"

def test_parser_nifty_pe():
    text = "NIFTY 23500 PE 15 Sept 26 Expiry\nBuy above 150\nSL below 144\nTgt above 170\nCMP 150"
    res = parse_message(text)
    assert res.parsed_successfully
    assert res.signal.option_type == "PE"

def test_parser_sensex_ce():
    text = "SENSEX 74000 CE 15 Sept 26 Expiry\nBuy above 420\nSL below 355\nTgt above 585\nCMP 420"
    res = parse_message(text)
    assert res.parsed_successfully
    assert res.signal.underlying == "SENSEX"
    assert res.signal.strike == 74000
    assert res.signal.option_type == "CE"

def test_parser_sensex_pe():
    text = "SENSEX 74000 PE 15 Sept 26 Expiry\nBuy above 420\nSL below 355\nTgt above 585\nCMP 420"
    res = parse_message(text)
    assert res.parsed_successfully
    assert res.signal.option_type == "PE"

def test_parser_sensex_without_expiry():
    text = "SENSEX 74000 CE\nBuy above 420\nSL below 355\nTgt above 585\nCMP 420"
    res = parse_message(text)
    assert res.parsed_successfully
    assert res.signal.expiry is None

def test_parser_sensex_lowercase():
    text = "sensex 74000 ce\nbuy above 420\nsl below 355\ntgt above 585\ncmp 420"
    res = parse_message(text)
    assert res.parsed_successfully
    assert res.signal.underlying == "SENSEX"
    assert res.signal.option_type == "CE"

def test_parser_sensex_mixed_case():
    text = "Sensex 74000 Ce\nBuy above 420\nSL below 355\nTgt above 585"
    res = parse_message(text)
    assert res.parsed_successfully
    assert res.signal.underlying == "SENSEX"

def test_parser_extra_whitespace():
    text = "  SENSEX   74000   CE   \n Buy above 420 \n SL below 355 \n Tgt above 585 \n "
    res = parse_message(text)
    assert res.parsed_successfully
    assert res.signal.strike == 74000

def test_parser_missing_strike():
    text = "SENSEX CE\nBuy above 420\nSL below 355\nTgt above 585"
    res = parse_message(text)
    assert not res.parsed_successfully
    assert "Missing or invalid instrument line" in res.validation_errors[0]

def test_parser_unsupported_underlying():
    text = "BANKNIFTY 52000 CE\nBuy above 420\nSL below 355\nTgt above 585"
    res = parse_message(text)
    assert not res.parsed_successfully
    assert "UNSUPPORTED_UNDERLYING" in res.validation_errors[0]

def test_parser_disclaimer_text():
    text = "SENSEX 74000 CE\nBuy above 420\nSL below 355\nTgt above 585\nCMP 420\nProfessional Trader : Nayan Pokharkar\nhttps://nayanpokharkar.com"
    res = parse_message(text)
    assert res.parsed_successfully
    assert res.signal.target == 585
