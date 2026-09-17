from enum import Enum
from pydantic import BaseModel, model_validator, Field
from datetime import date
from decimal import Decimal
from typing import Optional, Union

class TelegramMessageType(str, Enum):
    NEW_SIGNAL = "NEW_SIGNAL"
    PRICE_UPDATE = "PRICE_UPDATE"
    PARTIAL_PROFIT = "PARTIAL_PROFIT"
    EXIT = "EXIT"
    STOP_LOSS = "STOP_LOSS"
    INFORMATIONAL = "INFORMATIONAL"
    UNKNOWN = "UNKNOWN"

class TradeSignal(BaseModel):
    underlying: str
    strike: int
    option_type: str  # CE | PE
    expiry: Optional[date] = None
    entry_trigger: Decimal
    entry_direction: str  # "ABOVE" or "BELOW"
    stop_loss: Decimal
    target: Decimal
    telegram_cmp: Optional[Decimal] = None
    raw_text: str

    @model_validator(mode='after')
    def validate_logic(self):
        if self.underlying.upper() not in ("NIFTY", "SENSEX"):
            raise ValueError(f"UNSUPPORTED_UNDERLYING: {self.underlying} is not supported.")
        if self.strike <= 0:
            raise ValueError("Strike must be greater than 0")
        if self.entry_trigger <= 0:
            raise ValueError("Entry trigger must be greater than 0")
        if self.stop_loss <= 0:
            raise ValueError("Stop loss must be greater than 0")
        if self.target <= 0:
            raise ValueError("Target must be greater than 0")
        if self.telegram_cmp is not None and self.telegram_cmp <= 0:
            raise ValueError("CMP must be greater than 0 if provided")
        if self.option_type not in ("CE", "PE"):
            raise ValueError("Option type must be either CE or PE")
        if self.entry_direction not in ("ABOVE", "BELOW"):
            raise ValueError("Entry direction must be ABOVE or BELOW")

        if self.option_type == "CE":
            if self.stop_loss >= self.entry_trigger:
                raise ValueError("For CE (long), stop loss must be below entry trigger")
            if self.target <= self.entry_trigger:
                raise ValueError("For CE (long), target must be above entry trigger")
        elif self.option_type == "PE":
            if self.stop_loss >= self.entry_trigger:
                raise ValueError("For PE (long put), stop loss must be below entry trigger in price terms")
            if self.target <= self.entry_trigger:
                raise ValueError("For PE (long put), target must be above entry trigger in price terms")
        
        return self

class PriceUpdate(BaseModel):
    from_price: Decimal
    to_price: Decimal

class ParseResult(BaseModel):
    message_type: TelegramMessageType
    parsed_successfully: bool
    signal: Optional[TradeSignal] = None
    price_update: Optional[PriceUpdate] = None
    validation_errors: Optional[list[str]] = None
    raw_text: str
