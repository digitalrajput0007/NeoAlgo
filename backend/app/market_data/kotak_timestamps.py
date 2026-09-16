"""
Kotak F&O timestamp utilities.

IMPORTANT — Kotak Epoch:
  Kotak Neo stores F&O expiry timestamps (lExpiryDate / pExpiryDate) using an
  internal epoch that is approximately 10 years BEHIND the standard Unix epoch
  (1970-01-01 UTC).

  Evidence: Official Kotak Neo Python SDK (kotakneoapi v3.0.6),
  neo_api_client/services/scrip_search.py line 84:
      df["pExpiryDate"] = df["pExpiryDate"] + pd.to_timedelta(315511200, unit="s")

  The commented line immediately above it reads:
      # df['pExpiryDate'] = df['pExpiryDate'] + pd.DateOffset(years=10)

  Therefore, to obtain a standard Unix timestamp from a Kotak F&O date field,
  add KOTAK_FNO_EPOCH_OFFSET_SECONDS to the raw value.

  Example:
      raw lExpiryDate  = 1475764200   → raw Unix date: 2016-10-06 (appears stale)
      + KOTAK_FNO_EPOCH_OFFSET_SECONDS = 315511200
      adjusted         = 1791275400   → 2026-10-06  (actual contract expiry)

SCOPE:
  This offset applies to:
    - lExpiryDate  (same raw value as pExpiryDate in nse_fo.csv)
    - pExpiryDate  (nse_fo.csv F&O segment)

  This offset does NOT apply to:
    - Non-numeric date strings (e.g. "06OCT2026")
    - Equity/CM segment timestamps (use different conventions)
    - Standard Unix timestamps from other APIs

  Always use normalize_kotak_fno_timestamp() rather than adding the offset
  inline so that future SDK changes are isolated to one place.
"""

from __future__ import annotations
import logging
from datetime import datetime, timezone
from typing import Optional

logger = logging.getLogger(__name__)

# ─── Kotak epoch offset (seconds) ─────────────────────────────────────────────
# Source: kotakneoapi v3.0.6 scrip_search.py line 84
#         pd.to_timedelta(315511200, unit="s")  ≈ 10 years
KOTAK_FNO_EPOCH_OFFSET_SECONDS: int = 315_511_200


def normalize_kotak_fno_timestamp(raw_value: int | str | None) -> Optional[int]:
    """
    Convert a raw Kotak F&O date field to a standard Unix timestamp (seconds).

    Kotak stores lExpiryDate / pExpiryDate approximately 10 years behind the
    standard Unix epoch.  This function applies the SDK-documented correction.

    Args:
        raw_value: The raw integer value from lExpiryDate or pExpiryDate,
                   or its string representation.  Non-numeric values return None.

    Returns:
        Standard Unix timestamp (int, seconds since 1970-01-01 UTC), or None
        if the input is invalid / non-numeric.

    Examples:
        >>> normalize_kotak_fno_timestamp(1475764200)
        1791275400
        >>> from datetime import datetime, timezone
        >>> datetime.fromtimestamp(1791275400, tz=timezone.utc).date()
        datetime.date(2026, 10, 6)
        >>> normalize_kotak_fno_timestamp("0")  # futures with no expiry
        >>> normalize_kotak_fno_timestamp("abc")  # non-numeric
    """
    if raw_value is None:
        return None
    s = str(raw_value).strip()
    if not s.isdigit():
        return None
    raw_int = int(s)
    if raw_int == 0:
        return None
    return raw_int + KOTAK_FNO_EPOCH_OFFSET_SECONDS


def kotak_fno_timestamp_to_date(raw_value: int | str | None) -> Optional[datetime]:
    """
    Convert a raw Kotak F&O date field to a timezone-aware UTC datetime.

    Returns None for invalid / non-numeric / zero inputs.
    """
    ts = normalize_kotak_fno_timestamp(raw_value)
    if ts is None:
        return None
    return datetime.fromtimestamp(ts, tz=timezone.utc)


def is_kotak_fno_contract_active(raw_expiry: int | str | None,
                                  current_unix: float | None = None) -> bool:
    """
    Return True if a Kotak F&O contract is still active (not yet expired).

    Args:
        raw_expiry:   Raw lExpiryDate or pExpiryDate value from the CSV.
        current_unix: Unix timestamp to compare against.  Defaults to now.

    Returns:
        True  — contract expiry is >= now (active / future).
        False — contract has expired, value is zero, or value is invalid.
    """
    import time
    if current_unix is None:
        current_unix = time.time()
    ts = normalize_kotak_fno_timestamp(raw_expiry)
    if ts is None:
        return False
    return ts > current_unix
