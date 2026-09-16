"""
Safe TOTP Diagnostics Script.
NEVER prints secrets, credentials, or 6-digit codes.
"""
import os
import sys
import base64
from datetime import datetime, timezone
from dotenv import dotenv_values

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.config import settings
import pyotp

def run_diagnostics():
    env_vals = dotenv_values(".env")
    
    # 1 & 2. Check variable names in .env
    has_secret_in_dotenv = "KOTAK_NEO_TOTP_SECRET" in env_vals
    raw_secret = env_vals.get("KOTAK_NEO_TOTP_SECRET", "")
    
    has_static_totp = "KOTAK_NEO_TOTP" in env_vals
    raw_static_totp = env_vals.get("KOTAK_NEO_TOTP", "")

    # Look for near-miss names in .env
    near_misses = [k for k in env_vals.keys() if "TOTP" in k.upper() and k not in ("KOTAK_NEO_TOTP_SECRET", "KOTAK_NEO_TOTP")]

    print("=" * 65)
    print("SAFE TOTP CONFIGURATION DIAGNOSTICS")
    print("=" * 65)
    
    print(f"1. KOTAK_NEO_TOTP_SECRET present in .env: {'YES' if has_secret_in_dotenv else 'NO'}")
    print(f"   settings.kotak_neo_totp_secret loaded:   {'YES' if bool(getattr(settings, 'kotak_neo_totp_secret', None)) else 'NO'}")
    print(f"   os.environ KOTAK_NEO_TOTP_SECRET:        {'YES' if bool(os.environ.get('KOTAK_NEO_TOTP_SECRET')) else 'NO'}")
    if near_misses:
        print(f"   Near-miss variable names found: {near_misses}")

    print(f"\n2. KOTAK_NEO_TOTP (static) present in .env: {'YES' if has_static_totp else 'NO'}")
    if has_static_totp:
        stripped_static = str(raw_static_totp).strip()
        print(f"   Static TOTP length: {len(stripped_static)}")
        print(f"   Static TOTP is 6 digits: {len(stripped_static) == 6 and stripped_static.isdigit()}")

    print(f"\n3. pyotp module installed: YES (version {getattr(pyotp, '__version__', 'unknown')})")

    if raw_secret:
        raw_str = str(raw_secret)
        has_quotes = raw_str.startswith(('"', "'")) and raw_str.endswith(('"', "'"))
        has_spaces = " " in raw_str
        has_newlines = "\n" in raw_str or "\r" in raw_str
        clean_secret = raw_str.strip().strip('"').strip("'").replace(" ", "").replace("-", "")

        print(f"\n4. Secret formatting:")
        print(f"   Raw secret length: {len(raw_str)}")
        print(f"   Clean secret length: {len(clean_secret)}")
        print(f"   Enclosed in quotes in .env: {'YES' if has_quotes else 'NO'}")
        print(f"   Contained spaces: {'YES' if has_spaces else 'NO'}")
        print(f"   Contained newlines: {'YES' if has_newlines else 'NO'}")

        # Test Base32 validity
        try:
            pad_len = (8 - (len(clean_secret) % 8)) % 8
            padded = clean_secret.upper() + ("=" * pad_len)
            decoded = base64.b32decode(padded, casefold=True)
            print(f"   Base32 decode check: VALID ({len(decoded)} bytes decoded)")
            base32_ok = True
        except Exception as ex:
            print(f"   Base32 decode check: INVALID ({type(ex).__name__}: {ex})")
            base32_ok = False

        # Test pyotp generation
        if base32_ok:
            try:
                totp = pyotp.TOTP(clean_secret)
                code = totp.now()
                print(f"\n5. pyotp.TOTP(secret).now() check:")
                print(f"   Generation status: SUCCESS")
                print(f"   Generated code length: {len(code)}")
                print(f"   Generated code is numeric: {code.isdigit()}")
                print(f"   Generated at UTC: {datetime.now(timezone.utc).isoformat()}")
            except Exception as ex:
                print(f"\n5. pyotp generation error: {ex}")
    else:
        print(f"\n4. Secret formatting: N/A (KOTAK_NEO_TOTP_SECRET not found in .env)")

    # System clock check
    now_utc = datetime.now(timezone.utc)
    print(f"\n8. System clock:")
    print(f"   UTC timestamp: {now_utc.isoformat()}")
    print(f"   Local timestamp: {datetime.now().isoformat()}")
    
    # Check internet NTP / time sync estimate using worldtimeapi or similar HTTP header if possible
    try:
        import httpx
        resp = httpx.get("https://mis.kotaksecurities.com", timeout=3.0)
        server_date = resp.headers.get("date")
        print(f"   Kotak server header Date: {server_date}")
    except Exception:
        pass

    # Check precedence in kotak_neo.py
    print(f"\n9. Precedence in KotakNeoBroker.authenticate():")
    if raw_secret:
        print("   -> effective_secret will be selected (generates fresh code)")
    elif has_static_totp:
        print("   -> effective_totp will be selected (STATIC 6-DIGIT VALUE from .env)")
    else:
        print("   -> NEITHER secret NOR static totp available")

    print("=" * 65)

if __name__ == "__main__":
    run_diagnostics()
