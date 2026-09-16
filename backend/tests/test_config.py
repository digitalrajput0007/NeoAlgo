import pytest
import os
from pydantic_core._pydantic_core import ValidationError
from typing import Optional

def test_config_accepts_valid_kotak_keys(monkeypatch):
    monkeypatch.setenv("KOTAK_NEO_CONSUMER_KEY", "test_consumer")
    monkeypatch.setenv("KOTAK_NEO_MOBILE_NUMBER", "9999999999")
    monkeypatch.setenv("KOTAK_NEO_UCC", "TEST1234")
    monkeypatch.setenv("KOTAK_NEO_TOTP", "SECRET123")
    monkeypatch.setenv("KOTAK_NEO_MPIN", "123456")
    
    from app.config import Settings
    # override env_file so it doesn't read the real .env
    s = Settings(_env_file=None)
    
    assert s.kotak_neo_consumer_key == "test_consumer"
    assert s.kotak_neo_mobile_number == "9999999999"
    assert s.kotak_neo_ucc == "TEST1234"
    assert s.kotak_neo_totp is not None
    assert s.kotak_neo_mpin is not None

def test_config_forbids_extra_keys(monkeypatch):
    from app.config import Settings
    with pytest.raises(ValidationError) as exc:
        # Pass an extra explicit kwarg to trigger the extra=forbid validation
        s = Settings(_env_file=None, unknown_key="random")
    
    assert "Extra inputs are not permitted" in str(exc.value)

def test_config_missing_variables_do_not_crash(monkeypatch):
    # Ensure they are unset in env
    monkeypatch.delenv("KOTAK_NEO_CONSUMER_KEY", raising=False)
    monkeypatch.delenv("KOTAK_NEO_MOBILE_NUMBER", raising=False)
    
    from app.config import Settings
    s = Settings(_env_file=None)
    
    assert s.kotak_neo_consumer_key is None
    assert s.kotak_neo_mobile_number is None
