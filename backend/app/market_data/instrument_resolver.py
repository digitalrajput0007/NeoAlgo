import csv
import os
import logging
import httpx
import tempfile
import shutil
from typing import Dict, Any
from datetime import datetime
from app.market_data.kotak_timestamps import (
    is_kotak_fno_contract_active,
    normalize_kotak_fno_timestamp,
    KOTAK_FNO_EPOCH_OFFSET_SECONDS,
)

logger = logging.getLogger(__name__)

class InstrumentResolver:
    """
    Parses Kotak Neo Instrument Master (CSV) to resolve Telegram signals 
    (NIFTY 23500 CE) to valid broker instrument tokens.
    """
    def __init__(self, file_path: str = "data/instruments.csv"):
        self.file_path = file_path
        self._cache = []
        # Official Kotak Scrip Master download URL (can be updated if it changes)
        self.download_url = "https://lapi.kotaksecurities.com/api/v2/instruments/scrip-master.csv"

    def initialize(self):
        """Called at startup to load the instrument master."""
        self._load_instruments()



    def _load_instruments(self):
        full_path = os.path.join(os.getcwd(), self.file_path)
        if not os.path.exists(full_path):
            logger.error(f"INSTRUMENT_MASTER_UNAVAILABLE: File not found at {full_path}")
            return

        try:
            with open(full_path, mode='r', encoding='utf-8', errors='replace') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    # Kotak headers often have spaces (e.g. 'lExpiryDate ') or semicolons (e.g. 'dStrikePrice;')
                    clean_row = {k.strip().replace(';', ''): v for k, v in row.items() if k is not None}
                    self._cache.append(clean_row)
            logger.info(f"Loaded {len(self._cache)} instruments from master.")
        except Exception as e:
            logger.error(f"Failed to load instrument master: {e}")

    async def resolve_option_contract(self, underlying: str, strike: float, option_type: str, expiry: str = None) -> Dict[str, Any]:
        """
        Exact match resolution if expiry provided, otherwise nearest future weekly expiry.
        Never guesses fuzzy matching. Never hallucinates tokens.

        Kotak F&O timestamps (lExpiryDate / pExpiryDate) use a non-standard epoch
        approximately 10 years behind Unix. All comparisons use
        is_kotak_fno_contract_active() which applies the SDK-documented correction.
        """
        if not self._cache:
            raise RuntimeError("INSTRUMENT_MASTER_UNAVAILABLE: Cannot resolve instruments without a valid master file.")

        candidates = []

        for inst in self._cache:
            try:
                # Flexible extraction for Kotak's specific CSV format
                inst_underlying = str(inst.get("pSymbolName", inst.get("instrument_name", ""))).upper()

                inst_strike_val = inst.get("dStrikePrice", inst.get("pStrikePrice", inst.get("strike", "-1")))
                inst_strike = float(inst_strike_val) if inst_strike_val else -1

                # Kotak dStrikePrice is in paisa (×100); divide to get rupees.
                if "dStrikePrice" in inst and inst_strike > 0:
                    inst_strike = inst_strike / 100.0

                inst_type       = str(inst.get("pOptionType", inst.get("option_type", ""))).upper()
                inst_expiry_str = str(inst.get("pExpiryDate", inst.get("expiry_date", "")))
                raw_expiry      = inst.get("lExpiryDate") or inst.get("pExpiryDate", "")

                if (inst_underlying == underlying.upper() and
                        inst_strike == float(strike) and
                        inst_type == option_type.upper()):

                    contract_active = is_kotak_fno_contract_active(raw_expiry)
                    normalized_ts   = normalize_kotak_fno_timestamp(raw_expiry)  # for sorting

                    lot_size_val = inst.get("lLotSize") or inst.get("iLotSize") or "1"
                    try:
                        lot_size = int(float(str(lot_size_val).strip()))
                    except Exception:
                        lot_size = 1

                    if expiry:
                        from app.market_data.kotak_timestamps import kotak_fno_timestamp_to_date
                        date_obj = kotak_fno_timestamp_to_date(raw_expiry)
                        iso_date = date_obj.strftime("%Y-%m-%d") if date_obj else ""
                        dmy_date = date_obj.strftime("%d-%m-%Y") if date_obj else ""

                        is_match = (
                            inst_expiry_str == str(expiry) or
                            (iso_date and str(expiry) == iso_date) or
                            (dmy_date and str(expiry) == dmy_date)
                        )
                        if is_match:
                            if not contract_active:
                                raise RuntimeError(
                                    f"INSTRUMENT_EXPIRED: The explicitly requested expiry {expiry} has expired."
                                )
                            return {
                                "instrument_token": str(inst.get("pSymbol", inst.get("instrument_token"))),
                                "pSymbol":          str(inst.get("pSymbol", inst.get("instrument_token"))),
                                "symbol":           inst.get("pTrdSymbol", inst.get("instrument_name")),
                                "pTrdSymbol":       inst.get("pTrdSymbol", inst.get("instrument_name")),
                                "exchange_segment": inst.get("pExchSeg", inst.get("exchange_segment")),
                                "pExchSeg":         inst.get("pExchSeg", inst.get("exchange_segment")),
                                "expiry":           inst_expiry_str,
                                "lot_size":         lot_size,
                                "underlying":       inst_underlying,
                                "strike":           inst_strike,
                                "option_type":      inst_type,
                                "selection_mode":   "EXPLICIT_EXPIRY",
                            }
                    else:
                        # Auto-select: keep only active (future) contracts
                        if contract_active and normalized_ts:
                            candidates.append({
                                "token_data": {
                                    "instrument_token": str(inst.get("pSymbol", inst.get("instrument_token"))),
                                    "pSymbol":          str(inst.get("pSymbol", inst.get("instrument_token"))),
                                    "symbol":           inst.get("pTrdSymbol", inst.get("instrument_name")),
                                    "pTrdSymbol":       inst.get("pTrdSymbol", inst.get("instrument_name")),
                                    "exchange_segment": inst.get("pExchSeg", inst.get("exchange_segment")),
                                    "pExchSeg":         inst.get("pExchSeg", inst.get("exchange_segment")),
                                    "expiry":           inst_expiry_str,
                                    "lot_size":         lot_size,
                                    "underlying":       inst_underlying,
                                    "strike":           inst_strike,
                                    "option_type":      inst_type,
                                    "selection_mode":   "AUTO_SELECTED_NEAREST_WEEKLY_EXPIRY",
                                },
                                "expiry_ts": normalized_ts,
                            })
            except RuntimeError as re:
                raise ValueError(str(re))
            except Exception:
                continue

        if expiry:
            raise ValueError(f"No exact match found in instrument master for {underlying} {strike} {option_type} {expiry}")

        if not candidates:
            raise ValueError(f"INSTRUMENT_NOT_FOUND: No active future expiry found for {underlying} {strike} {option_type}")

        # Sort by normalized (corrected) expiry timestamp ascending; pick nearest
        candidates.sort(key=lambda x: x["expiry_ts"])
        
        if len(candidates) > 1 and candidates[0]["expiry_ts"] == candidates[1]["expiry_ts"]:
            # Check if they really have the same token/pSymbol. If not, it's ambiguous.
            if candidates[0]["token_data"]["pSymbol"] != candidates[1]["token_data"]["pSymbol"]:
                raise ValueError(f"AMBIGUOUS_INSTRUMENT: Multiple distinct contracts found with identical nearest expiry for {underlying} {strike} {option_type}")
                
        return candidates[0]["token_data"]
