"""
Central Timezone and Timestamp Utility for NeoAlgo Backend.

CANONICAL RULES:
1. All database models and persistent storage store canonical UTC.
2. Timestamps must never be stripped of timezone information during serialization.
3. Naive datetimes retrieved from storage (e.g. SQLite) are treated as UTC and serialized with explicit UTC offset (+00:00).
4. Timezone conversion to Asia/Kolkata (IST) is supported for display/formatting and reporting.
"""
from datetime import datetime, timezone
from typing import Optional, Union
from zoneinfo import ZoneInfo

# Canonical timezones
UTC = timezone.utc
IST = ZoneInfo("Asia/Kolkata")


def ensure_utc(dt: Optional[datetime]) -> Optional[datetime]:
    """
    Ensures a datetime is timezone-aware in UTC.
    If dt is naive, it assumes UTC.
    If dt is in another timezone, it converts to UTC.
    """
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC)


def to_utc_iso(dt: Optional[Union[datetime, str, int, float]]) -> Optional[str]:
    """
    Serializes any datetime/timestamp into an explicit UTC ISO-8601 string (+00:00).
    Never produces ambiguous naive strings like '2026-09-16T07:13:24'.
    """
    if dt is None:
        return None
    if isinstance(dt, (int, float)):
        # Epoch timestamp
        sec = dt if dt < 1e11 else dt / 1000.0
        return datetime.fromtimestamp(sec, tz=UTC).isoformat()
    if isinstance(dt, str):
        raw = dt.strip()
        if not raw or raw in ("null", "undefined", "—"):
            return None
        # If already formatted with timezone
        if raw.endswith("Z") or "+" in raw or "-" in raw[-6:]:
            return raw
        # If numeric string
        try:
            val = float(raw)
            sec = val if val < 1e11 else val / 1000.0
            return datetime.fromtimestamp(sec, tz=UTC).isoformat()
        except ValueError:
            pass
        # Naive ISO string -> append +00:00
        return f"{raw}+00:00"

    utc_dt = ensure_utc(dt)
    return utc_dt.isoformat() if utc_dt else None


def to_ist(dt: Optional[Union[datetime, str]]) -> Optional[datetime]:
    """
    Converts a datetime or ISO string to an Asia/Kolkata (IST) timezone-aware datetime.
    """
    if dt is None:
        return None
    if isinstance(dt, str):
        raw = dt.strip()
        if not raw:
            return None
        if not raw.endswith("Z") and "+" not in raw and "-" not in raw[-6:]:
            raw += "+00:00"
        try:
            parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
            return parsed.astimezone(IST)
        except Exception:
            return None
    
    utc_dt = ensure_utc(dt)
    return utc_dt.astimezone(IST) if utc_dt else None


def format_ist_datetime(dt: Optional[Union[datetime, str]], format_str: str = "%Y-%m-%d %I:%M:%S %p") -> str:
    """
    Formats a UTC datetime or ISO string in Asia/Kolkata (IST).
    Example output: '2026-09-16 12:43:24 PM'
    """
    ist_dt = to_ist(dt)
    if not ist_dt:
        return "—"
    return ist_dt.strftime(format_str)


def format_ist_time(dt: Optional[Union[datetime, str]], format_str: str = "%I:%M:%S %p") -> str:
    """
    Formats a UTC datetime or ISO string as time-only in Asia/Kolkata (IST).
    Example output: '12:43:24 PM'
    """
    return format_ist_datetime(dt, format_str=format_str)
