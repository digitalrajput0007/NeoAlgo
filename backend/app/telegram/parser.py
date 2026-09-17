import re
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Optional, Dict

from app.telegram.models import TelegramMessageType, TradeSignal, PriceUpdate, ParseResult
from pydantic import ValidationError

MONTH_MAP = {
    'jan': 1, 'january': 1,
    'feb': 2, 'february': 2,
    'mar': 3, 'march': 3,
    'apr': 4, 'april': 4,
    'may': 5,
    'jun': 6, 'june': 6,
    'jul': 7, 'july': 7,
    'aug': 8, 'august': 8,
    'sep': 9, 'sept': 9, 'september': 9,
    'oct': 10, 'october': 10,
    'nov': 11, 'november': 11,
    'dec': 12, 'december': 12
}

def parse_date(date_str: str) -> Optional[date]:
    """Parse string like '15 Sept 26' or '08 Sept 26' into a date object."""
    if not date_str:
        return None
    match = re.search(r'(\d{1,2})\s+([a-zA-Z]+)\s+(\d{2,4})', date_str)
    if not match:
        return None
    
    day_str, month_str, year_str = match.groups()
    try:
        day = int(day_str)
        month_idx = MONTH_MAP.get(month_str.lower())
        if not month_idx:
            return None
        
        year = int(year_str)
        if year < 100:
            year += 2000
            
        return date(year, month_idx, day)
    except Exception:
        return None

def classify_message(text: str) -> TelegramMessageType:
    text_lower = text.strip().lower()
    
    # Check for EXIT
    if text_lower == "exit":
        return TelegramMessageType.EXIT
        
    # Check for STOP LOSS
    if text_lower in ["sl hit", "sl hit.", "sl hit!"]:
        return TelegramMessageType.STOP_LOSS
        
    # Check for PARTIAL PROFIT
    if "book partial profit" in text_lower or "partial profit" in text_lower:
        return TelegramMessageType.PARTIAL_PROFIT
        
    # Check for PRICE UPDATE (e.g. From 36 to 58)
    if re.search(r'from\s+[\d.]+\s+to\s+[\d.]+', text_lower):
        return TelegramMessageType.PRICE_UPDATE
        
    # Check for INFORMATIONAL
    if "youtube" in text_lower or "youtu.be" in text_lower or "at " in text_lower or "-" in text_lower and not ("buy" in text_lower and "sl" in text_lower):
        # A bit generic, let's refine: if it doesn't look like a signal and has typical info keywords
        if not (re.search(r'buy\s+(above|below)', text_lower) and re.search(r'sl below', text_lower)):
            return TelegramMessageType.INFORMATIONAL

    # Check for NEW SIGNAL
    if re.search(r'buy\s+(above|below)', text_lower) and re.search(r'sl below', text_lower) and re.search(r'tgt above', text_lower):
        return TelegramMessageType.NEW_SIGNAL
        
    return TelegramMessageType.UNKNOWN

def parse_new_signal(text: str) -> TradeSignal:
    # NIFTY 23500 CE 15 Sept 26 Expiry
    # Buy above 150
    # SL below 144
    # Tgt above 170
    # CMP 150
    
    underlying_match = re.search(r'^[ \t]*([A-Za-z]+)[ \t]+(\d+)[ \t]+(CE|PE)(?:[ \t]+(.*?))?[ \t]*$', text, re.IGNORECASE | re.MULTILINE)
    if not underlying_match:
        raise ValueError("Missing or invalid instrument line (e.g. SENSEX 74000 CE or NIFTY 23500 PE 15 Sept 26 Expiry)")
    
    underlying = underlying_match.group(1).upper()
    strike = int(underlying_match.group(2))
    option_type = underlying_match.group(3).upper()
    expiry_str = underlying_match.group(4)
    
    expiry_date = parse_date(expiry_str) if expiry_str else None
    
    entry_match = re.search(r'buy\s+(above|below)\s+([\d.]+)', text, re.IGNORECASE)
    sl_match = re.search(r'sl below\s+([\d.]+)', text, re.IGNORECASE)
    tgt_match = re.search(r'tgt above\s+([\d.]+)', text, re.IGNORECASE)
    cmp_match = re.search(r'cmp\s+([\d.]+)', text, re.IGNORECASE)
    
    if not entry_match:
        raise ValueError("Missing 'Buy above <price>'")
    if not sl_match:
        raise ValueError("Missing 'SL below <price>'")
    if not tgt_match:
        raise ValueError("Missing 'Tgt above <price>'")
        
    try:
        entry_dir_str = entry_match.group(1).upper()
        entry_trigger = Decimal(entry_match.group(2))
        stop_loss = Decimal(sl_match.group(1))
        target = Decimal(tgt_match.group(1))
        telegram_cmp = Decimal(cmp_match.group(1)) if cmp_match else None
    except InvalidOperation:
        raise ValueError("Prices must be valid numbers")

    return TradeSignal(
        underlying=underlying,
        strike=strike,
        option_type=option_type,
        expiry=expiry_date,
        entry_trigger=entry_trigger,
        entry_direction=entry_dir_str,
        stop_loss=stop_loss,
        target=target,
        telegram_cmp=telegram_cmp,
        raw_text=text
    )

def parse_price_update(text: str) -> PriceUpdate:
    match = re.search(r'from\s+([\d.]+)\s+to\s+([\d.]+)', text, re.IGNORECASE)
    if not match:
        raise ValueError("Could not extract prices from price update")
    try:
        from_price = Decimal(match.group(1))
        to_price = Decimal(match.group(2))
    except InvalidOperation:
        raise ValueError("Prices must be valid numbers")
        
    return PriceUpdate(from_price=from_price, to_price=to_price)

def parse_message(text: str) -> ParseResult:
    msg_type = classify_message(text)
    
    if msg_type == TelegramMessageType.NEW_SIGNAL:
        try:
            signal = parse_new_signal(text)
            return ParseResult(message_type=msg_type, parsed_successfully=True, signal=signal, raw_text=text)
        except (ValueError, ValidationError) as e:
            errors = [str(e)]
            if isinstance(e, ValidationError):
                errors = [err["msg"] for err in e.errors()]
            return ParseResult(message_type=msg_type, parsed_successfully=False, validation_errors=errors, raw_text=text)
            
    elif msg_type == TelegramMessageType.PRICE_UPDATE:
        try:
            update = parse_price_update(text)
            return ParseResult(message_type=msg_type, parsed_successfully=True, price_update=update, raw_text=text)
        except ValueError as e:
            return ParseResult(message_type=msg_type, parsed_successfully=False, validation_errors=[str(e)], raw_text=text)
            
    # For EXIT, STOP_LOSS, PARTIAL_PROFIT, INFORMATIONAL, UNKNOWN there is no complex structured data yet
    return ParseResult(message_type=msg_type, parsed_successfully=True, raw_text=text)
