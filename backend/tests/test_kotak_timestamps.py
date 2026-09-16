"""
Unit tests for Kotak F&O timestamp epoch correction.
Tests prove the constant, the helper, and the resolver use the SDK-documented offset.
"""
import time
from datetime import date, datetime, timezone
import pytest
import pytest_asyncio

from app.market_data.kotak_timestamps import (
    KOTAK_FNO_EPOCH_OFFSET_SECONDS,
    normalize_kotak_fno_timestamp,
    kotak_fno_timestamp_to_date,
    is_kotak_fno_contract_active,
)
from app.market_data.instrument_resolver import InstrumentResolver


# ─── KOTAK_FNO_EPOCH_OFFSET_SECONDS ──────────────────────────────────────────

class TestKotakEpochConstant:
    def test_constant_value(self):
        """SDK scrip_search.py line 84 uses exactly 315511200."""
        assert KOTAK_FNO_EPOCH_OFFSET_SECONDS == 315_511_200

    def test_constant_is_approximately_10_years(self):
        """Offset is between 9.99 and 10.01 Julian years."""
        years = KOTAK_FNO_EPOCH_OFFSET_SECONDS / (365.25 * 86400)
        assert 9.99 < years < 10.01


# ─── normalize_kotak_fno_timestamp ───────────────────────────────────────────

class TestNormalizeKotakFnoTimestamp:
    def test_known_value_int(self):
        """Raw 1475764200 must normalize to 1791275400."""
        assert normalize_kotak_fno_timestamp(1475764200) == 1791275400

    def test_known_value_str(self):
        """String input must be accepted."""
        assert normalize_kotak_fno_timestamp("1475764200") == 1791275400

    def test_known_date_is_2026_10_06(self):
        """Normalized 1791275400 must decode to 2026-10-06 UTC."""
        ts = normalize_kotak_fno_timestamp(1475764200)
        dt = datetime.fromtimestamp(ts, tz=timezone.utc).date()
        assert dt == date(2026, 10, 6)

    def test_zero_returns_none(self):
        assert normalize_kotak_fno_timestamp(0) is None
        assert normalize_kotak_fno_timestamp("0") is None

    def test_none_returns_none(self):
        assert normalize_kotak_fno_timestamp(None) is None

    def test_non_numeric_string_returns_none(self):
        assert normalize_kotak_fno_timestamp("abc") is None
        assert normalize_kotak_fno_timestamp("06OCT2026") is None
        assert normalize_kotak_fno_timestamp("") is None


# ─── kotak_fno_timestamp_to_date ─────────────────────────────────────────────

class TestKotakFnoTimestampToDate:
    def test_returns_utc_datetime(self):
        dt = kotak_fno_timestamp_to_date(1475764200)
        assert dt is not None
        assert dt.tzinfo is not None
        assert dt.date() == date(2026, 10, 6)

    def test_invalid_returns_none(self):
        assert kotak_fno_timestamp_to_date(None) is None
        assert kotak_fno_timestamp_to_date("bad") is None


# ─── is_kotak_fno_contract_active ────────────────────────────────────────────

class TestIsKotakFnoContractActive:
    """
    REGRESSION TESTS:
    A NIFTY contract with lExpiryDate=1475764200 (raw appears as 2016-10-06,
    corrected is 2026-10-06) must NOT be treated as expired on 2026-09-16.
    """

    def test_known_future_contract_is_active(self):
        """lExpiryDate=1475764200 corrects to 2026-10-06 → active in Sep 2026."""
        # Simulate current time as 2026-09-16 00:00:00 UTC
        sep_16_2026 = datetime(2026, 9, 16, tzinfo=timezone.utc).timestamp()
        assert is_kotak_fno_contract_active(1475764200, current_unix=sep_16_2026) is True

    def test_known_future_contract_is_active_str(self):
        """String raw value must also work."""
        sep_16_2026 = datetime(2026, 9, 16, tzinfo=timezone.utc).timestamp()
        assert is_kotak_fno_contract_active("1475764200", current_unix=sep_16_2026) is True

    def test_raw_2016_value_without_correction_would_fail(self):
        """Prove the bug: raw comparison would incorrectly mark 2026 contract as expired."""
        sep_16_2026 = datetime(2026, 9, 16, tzinfo=timezone.utc).timestamp()
        raw = 1475764200
        # Without correction: raw < current_time → would be treated as expired
        assert raw < sep_16_2026, "Confirms the bug: raw value is before current time"
        # With correction: active
        assert is_kotak_fno_contract_active(raw, current_unix=sep_16_2026) is True

    def test_genuinely_expired_contract(self):
        """A contract that expired in 2025 must be inactive in 2026."""
        # Raw value that corrects to 2025-06-30
        # 2025-06-30 UTC in standard Unix = 1751241600
        # raw = 1751241600 - 315511200 = 1435730400
        raw_expired = 1751241600 - KOTAK_FNO_EPOCH_OFFSET_SECONDS
        sep_16_2026 = datetime(2026, 9, 16, tzinfo=timezone.utc).timestamp()
        assert is_kotak_fno_contract_active(raw_expired, current_unix=sep_16_2026) is False

    def test_zero_expiry_is_inactive(self):
        assert is_kotak_fno_contract_active(0) is False
        assert is_kotak_fno_contract_active("0") is False

    def test_none_expiry_is_inactive(self):
        assert is_kotak_fno_contract_active(None) is False

    def test_non_numeric_is_inactive(self):
        assert is_kotak_fno_contract_active("abc") is False

    def test_uses_real_current_time_by_default(self):
        """Without current_unix arg, defaults to now (not a fixed date)."""
        # A contract expiring 10 years from now in Kotak raw = standard_now + 10yr - offset ≈ standard_now
        future_standard_ts = time.time() + 365 * 86400  # expires in 1 year
        raw_future = int(future_standard_ts) - KOTAK_FNO_EPOCH_OFFSET_SECONDS
        assert is_kotak_fno_contract_active(raw_future) is True


# ─── InstrumentResolver — epoch-corrected auto-selection ─────────────────────

class TestInstrumentResolverEpochFix:
    """
    Verifies that InstrumentResolver correctly selects contracts using
    the Kotak epoch-corrected timestamp, NOT the raw value.
    """
    STRIKE = 24500.0
    # raw lExpiryDate that corrects to 2026-10-02 (active on 2026-09-16)
    # standard Unix 2026-10-02 = 1790524800
    # raw = 1790524800 - 315511200 = 1475013600
    RAW_ACTIVE_EXPIRY   = str(1790524800 - KOTAK_FNO_EPOCH_OFFSET_SECONDS)
    # raw lExpiryDate that corrects to 2025-06-30 (expired on 2026-09-16)
    RAW_EXPIRED_EXPIRY  = str(1751241600 - KOTAK_FNO_EPOCH_OFFSET_SECONDS)

    def _make_row(self, raw_expiry, option_type="CE", strike=None):
        if strike is None:
            strike = self.STRIKE * 100  # in paisa
        return {
            "pSymbolName": "NIFTY",
            "pExchSeg":    "nse_fo",
            "pOptionType": option_type,
            "dStrikePrice": str(strike),
            "lExpiryDate":  raw_expiry,
            "pExpiryDate":  raw_expiry,
            "pSymbol":      "99999",
            "pTrdSymbol":   f"NIFTY26OCT{int(self.STRIKE)}{option_type}",
        }

    @pytest.mark.asyncio
    async def test_active_contract_selected(self):
        resolver = InstrumentResolver.__new__(InstrumentResolver)
        resolver._cache = [self._make_row(self.RAW_ACTIVE_EXPIRY)]
        result = await resolver.resolve_option_contract("NIFTY", self.STRIKE, "CE")
        assert result["instrument_token"] == "99999"
        assert result["selection_mode"] == "AUTO_SELECTED_NEAREST_WEEKLY_EXPIRY"

    @pytest.mark.asyncio
    async def test_expired_contract_not_selected(self):
        resolver = InstrumentResolver.__new__(InstrumentResolver)
        resolver._cache = [self._make_row(self.RAW_EXPIRED_EXPIRY)]
        with pytest.raises(ValueError, match="INSTRUMENT_NOT_FOUND"):
            await resolver.resolve_option_contract("NIFTY", self.STRIKE, "CE")

    @pytest.mark.asyncio
    async def test_nearest_expiry_chosen_correctly(self):
        """When two active contracts exist, the nearer expiry is returned."""
        # raw_near corrects to 2026-09-25, raw_far to 2026-10-30
        raw_near = str(int(datetime(2026, 9, 25, tzinfo=timezone.utc).timestamp()) - KOTAK_FNO_EPOCH_OFFSET_SECONDS)
        raw_far  = str(int(datetime(2026, 10, 30, tzinfo=timezone.utc).timestamp()) - KOTAK_FNO_EPOCH_OFFSET_SECONDS)
        resolver = InstrumentResolver.__new__(InstrumentResolver)
        resolver._cache = [
            {**self._make_row(raw_far,  "CE"), "pSymbol": "FAR",  "pTrdSymbol": "NIFTY26OCT24500CE"},
            {**self._make_row(raw_near, "CE"), "pSymbol": "NEAR", "pTrdSymbol": "NIFTY26SEP24500CE"},
        ]
        result = await resolver.resolve_option_contract("NIFTY", self.STRIKE, "CE")
        assert result["instrument_token"] == "NEAR"

    @pytest.mark.asyncio
    async def test_stale_master_rejects_all(self):
        """
        Regression: stale 2016 master (raw values ARE 2016 standard Unix) must
        be rejected, because without the offset they would not pass active check.
        Stale 2016 timestamp as raw (already in standard Unix → no Kotak epoch):
        Using 2016-10-06 standard Unix = 1475726400. After adding offset that
        would be 2026-ish. So to simulate a genuine 2016 data row that should
        be rejected: use a value that even after offset is still in the past.
        Past corrected = standard 2010-01-01 Unix → raw = 1262304000 - 315511200 = 946792800
        """
        raw_2010 = str(1262304000 - KOTAK_FNO_EPOCH_OFFSET_SECONDS)
        resolver = InstrumentResolver.__new__(InstrumentResolver)
        resolver._cache = [self._make_row(raw_2010)]
        with pytest.raises(ValueError, match="INSTRUMENT_NOT_FOUND"):
            await resolver.resolve_option_contract("NIFTY", self.STRIKE, "CE")
