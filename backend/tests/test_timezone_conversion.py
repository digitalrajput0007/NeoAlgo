"""
Comprehensive Unit Tests for UTC Canonical Storage and Asia/Kolkata (IST) Display.
Validates Task 2, Task 6, Task 7, Task 8, and Task 9.
"""
import pytest
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
from app.utils.timezone import (
    to_utc_iso,
    to_ist,
    format_ist_datetime,
    format_ist_time,
    ensure_utc,
    UTC,
    IST
)


class TestTimezoneConversion:
    """Test suite proving explicit UTC canonical serialization and Asia/Kolkata (IST) formatting."""

    def test_utc_to_ist_exact_conversion(self):
        """Task 9: Proves UTC 2026-09-16T07:13:24Z renders in IST as 2026-09-16 12:43:24 PM."""
        iso_z = "2026-09-16T07:13:24Z"
        formatted_dt = format_ist_datetime(iso_z)
        formatted_time = format_ist_time(iso_z)

        assert formatted_dt == "2026-09-16 12:43:24 PM"
        assert formatted_time == "12:43:24 PM"

    def test_midnight_utc_crossing_into_ist(self):
        """Midnight UTC (20:00:00Z) crosses into the next day in IST (+5:30 -> 01:30:00 AM next day)."""
        midnight_utc = "2026-09-16T20:00:00Z"
        formatted = format_ist_datetime(midnight_utc)
        assert formatted == "2026-09-17 01:30:00 AM"

    def test_date_rollover_late_night(self):
        """Late night UTC (23:45:00Z) rolls over date into next day IST (+5:30 -> 05:15:00 AM next day)."""
        late_utc = "2026-09-16T23:45:00Z"
        formatted = format_ist_datetime(late_utc)
        assert formatted == "2026-09-17 05:15:00 AM"

    def test_timestamps_with_plus_zero_offset(self):
        """Explicit +00:00 offset is correctly interpreted as UTC and converted to IST."""
        iso_plus_zero = "2026-09-16T07:13:24+00:00"
        formatted = format_ist_datetime(iso_plus_zero)
        assert formatted == "2026-09-16 12:43:24 PM"

    def test_timestamps_already_containing_ist_offset(self):
        """Timestamps already containing +05:30 offset preserve the exact moment in time."""
        iso_ist = "2026-09-16T12:43:24+05:30"
        formatted = format_ist_datetime(iso_ist)
        assert formatted == "2026-09-16 12:43:24 PM"

    def test_naive_timestamp_handling(self):
        """Naive timestamps from database storage are treated as canonical UTC without timezone loss."""
        naive_dt = datetime(2026, 9, 16, 7, 13, 24)
        iso_serialized = to_utc_iso(naive_dt)

        # Must include explicit +00:00 offset
        assert iso_serialized == "2026-09-16T07:13:24+00:00"

        # Formats to 12:43:24 PM IST
        assert format_ist_datetime(naive_dt) == "2026-09-16 12:43:24 PM"
        assert format_ist_datetime("2026-09-16 07:13:24") == "2026-09-16 12:43:24 PM"

    def test_invalid_and_empty_timestamp_handling(self):
        """Invalid or empty timestamp inputs return fallback without raising exceptions."""
        assert format_ist_datetime(None) == "—"
        assert format_ist_datetime("") == "—"
        assert format_ist_datetime("invalid_timestamp") == "—"
        assert format_ist_time(None) == "—"
        assert format_ist_time("null") == "—"

    def test_sfeed_timestamps(self):
        """SFeed numeric epoch timestamps in seconds/milliseconds are converted cleanly to IST."""
        # 1789542804 corresponds to 2026-09-16 07:13:24 UTC
        epoch_sec = 1789542804
        utc_iso = to_utc_iso(epoch_sec)
        assert "2026-09-16T07:13:24" in utc_iso
        assert utc_iso.endswith("+00:00") or utc_iso.endswith("Z")

        formatted = format_ist_datetime(utc_iso)
        assert formatted == "2026-09-16 12:43:24 PM"

    def test_telegram_message_timestamp_normalization(self):
        """Telethon timezone-aware or naive message timestamps are normalized to UTC at the boundary."""
        # Simulate Telethon returning timezone-aware UTC datetime
        telethon_dt = datetime(2026, 9, 16, 7, 13, 24, tzinfo=timezone.utc)
        normalized = ensure_utc(telethon_dt)
        assert normalized.tzinfo == timezone.utc
        assert to_utc_iso(normalized) == "2026-09-16T07:13:24+00:00"
        assert format_ist_datetime(normalized) == "2026-09-16 12:43:24 PM"

    def test_audit_log_timestamp(self):
        """Audit log creation timestamps serialize with timezone and format cleanly in IST."""
        audit_dt = datetime(2026, 9, 16, 7, 13, 24, 500000, tzinfo=timezone.utc)
        iso_str = to_utc_iso(audit_dt)
        assert "+00:00" in iso_str
        assert format_ist_datetime(iso_str) == "2026-09-16 12:43:24 PM"

    @pytest.mark.asyncio
    async def test_api_contract_preserves_timezone_offset(self):
        """Task 6: FastAPI endpoints return explicit timezone-aware ISO strings."""
        from httpx import AsyncClient, ASGITransport
        from app.main import app

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            res = await ac.get("/api/signals")
            assert res.status_code == 200
            signals = res.json()
            for sig in signals[:5]:
                ts = sig.get("timestamp")
                if ts:
                    # Must contain timezone information (+ or Z)
                    assert "+" in ts or ts.endswith("Z"), f"Signal timestamp {ts} lacks explicit timezone offset"
