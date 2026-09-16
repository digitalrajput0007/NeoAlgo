"""
Download and inspect the actual current Kotak NSE F&O Scrip Master CSV.
Reports structure, NIFTY rows, expiry format, strike format, option type representation.
Never prints credentials or tokens.
"""
import asyncio
import httpx
import io
import time
import csv
import json
from datetime import datetime, timezone
from collections import Counter

CSV_URL = "https://lapi.kotaksecurities.com/wso2-scripmaster/v1/prod/2026-09-16/transformed/nse_fo.csv"

async def main():
    print("=" * 60)
    print("STEP 1 — Download current NSE F&O Scrip Master")
    print(f"URL: {CSV_URL}")
    print("=" * 60)

    async with httpx.AsyncClient(timeout=60.0, follow_redirects=True) as client:
        r = await client.get(CSV_URL)
        print(f"HTTP STATUS: {r.status_code}")
        print(f"CONTENT-TYPE: {r.headers.get('content-type', 'N/A')}")
        if r.status_code != 200:
            print("DOWNLOAD FAILED. Cannot continue.")
            print("BODY:", r.text[:500])
            return

    content = r.content
    file_size_kb = len(content) / 1024
    print(f"FILE SIZE: {file_size_kb:.1f} KB ({len(content)} bytes)")

    # ── Parse CSV ─────────────────────────────────────────────────────────────
    print("\n" + "=" * 60)
    print("STEP 2 — CSV Structure")
    print("=" * 60)

    text = content.decode("utf-8", errors="replace")
    reader = csv.DictReader(io.StringIO(text))
    all_rows = list(reader)

    columns = reader.fieldnames or []
    print(f"TOTAL ROWS:   {len(all_rows)}")
    print(f"TOTAL COLS:   {len(columns)}")
    print(f"\nCOLUMN NAMES:")
    for col in columns:
        print(f"  {repr(col)}")

    print(f"\nFIRST 3 ROWS (raw):")
    for i, row in enumerate(all_rows[:3]):
        print(f"\n  --- Row {i+1} ---")
        for k, v in row.items():
            print(f"    {repr(k)}: {repr(v)}")

    # ── Clean column names (strip BOM/whitespace/semicolons) ──────────────────
    def clean_row(row):
        return {k.strip().lstrip('\ufeff').replace(';', ''): (v or '').strip()
                for k, v in row.items() if k is not None}

    rows = [clean_row(r) for r in all_rows]
    clean_cols = list(rows[0].keys()) if rows else []

    print(f"\nCLEAN COLUMN NAMES (after strip/BOM removal):")
    for col in clean_cols:
        print(f"  {repr(col)}")

    # ── Key fields inspection ─────────────────────────────────────────────────
    KEY_FIELDS = ["pSymbolName", "pSymbol", "pExchSeg", "pTrdSymbol",
                  "lLotSize", "lExpiryDate", "dStrikePrice", "pOptionType",
                  "pExpiryDate", "pSeries"]

    print(f"\n" + "=" * 60)
    print("STEP 3 — Key Fields: Sample Values")
    print("=" * 60)
    for field in KEY_FIELDS:
        if field in clean_cols:
            vals = [r[field] for r in rows if r.get(field, "").strip()]
            unique = list(dict.fromkeys(vals[:20]))  # first 20 unique-ish
            print(f"\n  {field}:")
            print(f"    Present: YES  |  Non-empty sample (up to 5): {unique[:5]}")
        else:
            print(f"\n  {field}: NOT FOUND in CSV columns")

    # ── pExchSeg unique values ────────────────────────────────────────────────
    print(f"\n" + "=" * 60)
    print("STEP 4 — pExchSeg unique values (all)")
    print("=" * 60)
    seg_counts = Counter(r.get("pExchSeg", "") for r in rows)
    for seg, cnt in seg_counts.most_common():
        print(f"  {repr(seg)}: {cnt} rows")

    # ── NIFTY row counts ─────────────────────────────────────────────────────
    print(f"\n" + "=" * 60)
    print("STEP 5 — NIFTY Row Counts")
    print("=" * 60)

    sym_exact   = [r for r in rows if r.get("pSymbolName", "").upper().strip() == "NIFTY"]
    sym_contains = [r for r in rows if "NIFTY" in r.get("pSymbolName", "").upper()]
    trd_contains = [r for r in rows if "NIFTY" in r.get("pTrdSymbol", "").upper()]

    print(f"  pSymbolName == 'NIFTY' (exact):    {len(sym_exact)}")
    print(f"  pSymbolName contains 'NIFTY':      {len(sym_contains)}")
    print(f"  pTrdSymbol  contains 'NIFTY':      {len(trd_contains)}")

    # ── Unique pSymbolName values containing NIFTY ───────────────────────────
    nifty_syms = sorted(set(r.get("pSymbolName","").strip() for r in sym_contains))
    print(f"\n  Unique pSymbolName values containing NIFTY:")
    for s in nifty_syms[:20]:
        print(f"    {repr(s)}")

    # ── Expiry format investigation on NIFTY rows ────────────────────────────
    print(f"\n" + "=" * 60)
    print("STEP 6 — Expiry Format Inspection (NIFTY rows)")
    print("=" * 60)

    current_unix = time.time()
    today = datetime.now(timezone.utc).date()
    print(f"  Today (UTC):         {today}")
    print(f"  Current unix ts:     {int(current_unix)}")
    print(f"  Current unix ms:     {int(current_unix * 1000)}")

    if sym_exact:
        print(f"\n  Sample lExpiryDate values from pSymbolName=='NIFTY' rows (first 10):")
        seen = set()
        for r in sym_exact:
            val = r.get("lExpiryDate", "N/A").strip()
            pexp = r.get("pExpiryDate", "N/A").strip()
            if val not in seen:
                seen.add(val)
                # Try to interpret
                interpretation = "?"
                if val.isdigit():
                    v = int(val)
                    # Unix seconds? (reasonable range 2020-2035)
                    if 1577836800 < v < 2051222400:
                        interpretation = f"Unix-secs -> {datetime.fromtimestamp(v, tz=timezone.utc).date()}"
                    # Unix milliseconds?
                    elif 1577836800000 < v < 2051222400000:
                        interpretation = f"Unix-ms -> {datetime.fromtimestamp(v/1000, tz=timezone.utc).date()}"
                    # YYYYMMDD?
                    elif 20200101 <= v <= 20351231:
                        interpretation = f"YYYYMMDD -> {str(v)[:4]}-{str(v)[4:6]}-{str(v)[6:]}"
                    else:
                        interpretation = f"Unknown int: {v}"
                else:
                    interpretation = f"Non-numeric: {repr(val)}"
                print(f"    lExpiryDate={repr(val)} | pExpiryDate={repr(pexp)} | => {interpretation}")
            if len(seen) >= 10:
                break

    # ── dStrikePrice format ───────────────────────────────────────────────────
    print(f"\n" + "=" * 60)
    print("STEP 7 — Strike Price Format (NIFTY rows)")
    print("=" * 60)
    print(f"  Documentation says: dStrikePrice / 100 = actual strike")
    if sym_exact:
        seen = set()
        for r in sym_exact[:30]:
            sp = r.get("dStrikePrice", "").strip()
            trd = r.get("pTrdSymbol", "").strip()
            if sp and sp not in seen:
                seen.add(sp)
                try:
                    raw = float(sp)
                    divided = raw / 100
                    print(f"    dStrikePrice={repr(sp)} => /100 = {divided} | pTrdSymbol={repr(trd)}")
                except ValueError:
                    print(f"    dStrikePrice={repr(sp)} (non-numeric) | pTrdSymbol={repr(trd)}")
            if len(seen) >= 8:
                break

    # ── Option type representation ────────────────────────────────────────────
    print(f"\n" + "=" * 60)
    print("STEP 8 — Option Type Representation (NIFTY rows)")
    print("=" * 60)
    opt_types = Counter(r.get("pOptionType","").strip() for r in sym_exact)
    print(f"  pOptionType values in NIFTY rows: {dict(opt_types)}")
    # Also check pTrdSymbol suffixes
    trd_suffixes = Counter()
    for r in sym_exact:
        trd = r.get("pTrdSymbol","").strip()
        if trd.endswith("CE") or trd.endswith("PE"):
            trd_suffixes[trd[-2:]] += 1
        else:
            trd_suffixes["OTHER"] += 1
    print(f"  pTrdSymbol suffix CE/PE counts:   {dict(trd_suffixes)}")

    # ── Future expiry check: the EXACT logic our code uses ───────────────────
    print(f"\n" + "=" * 60)
    print("STEP 9 — Exact Replication of Our Validation Logic")
    print("=" * 60)
    print("  Our code checks: lExpiryDate as integer Unix-seconds > current_time")
    found_by_current_logic = False
    reasons_failed = []
    for r in sym_exact[:50]:  # sample first 50
        expiry_str = r.get("pExpiryDate", "").strip()
        expiry_ts = 0
        lexp = r.get("lExpiryDate", "").strip()
        if lexp.isdigit():
            expiry_ts = int(lexp)
        elif expiry_str.isdigit():
            expiry_ts = int(expiry_str)

        if expiry_ts > current_unix:
            found_by_current_logic = True
            break
        else:
            if expiry_ts == 0:
                reasons_failed.append(f"expiry_ts=0 (lExpiryDate={repr(lexp)}, pExpiryDate={repr(expiry_str)})")
            else:
                reasons_failed.append(f"expiry_ts={expiry_ts} <= current_unix={int(current_unix)}")

    print(f"  RESULT: {'FOUND (logic is correct)' if found_by_current_logic else 'NOT FOUND (logic is broken)'}")
    if not found_by_current_logic and reasons_failed:
        print(f"  SAMPLE FAILURES (first 5):")
        for f in reasons_failed[:5]:
            print(f"    {f}")

    # ── Future NIFTY contracts: correct interpretation ────────────────────────
    print(f"\n" + "=" * 60)
    print("STEP 10 — Future NIFTY Contracts (correct date parsing)")
    print("=" * 60)
    future_rows = []
    for r in sym_exact:
        lexp = r.get("lExpiryDate", "").strip()
        if not lexp.isdigit():
            continue
        v = int(lexp)
        # Determine correct interpretation
        if 1577836800 < v < 2051222400:             # Unix seconds
            expiry_date = datetime.fromtimestamp(v, tz=timezone.utc).date()
        elif 1577836800000 < v < 2051222400000:     # Unix milliseconds
            expiry_date = datetime.fromtimestamp(v / 1000, tz=timezone.utc).date()
        elif 20200101 <= v <= 20351231:             # YYYYMMDD
            expiry_date = datetime(int(str(v)[:4]), int(str(v)[4:6]), int(str(v)[6:]), tzinfo=timezone.utc).date()
        else:
            continue
        if expiry_date >= today:
            future_rows.append((expiry_date, r))

    future_rows.sort(key=lambda x: x[0])
    expiry_dates = sorted(set(d for d, _ in future_rows))
    ce_rows = [(d, r) for d, r in future_rows if r.get("pTrdSymbol","").endswith("CE") or r.get("pOptionType","").upper() == "CE"]
    pe_rows = [(d, r) for d, r in future_rows if r.get("pTrdSymbol","").endswith("PE") or r.get("pOptionType","").upper() == "PE"]
    fut_rows = [(d, r) for d, r in future_rows if r.get("pOptionType","").upper() in ("", "XX", "N/A", "NONE") and not r.get("pTrdSymbol","").endswith(("CE","PE"))]

    print(f"  Total NIFTY rows with future expiry: {len(future_rows)}")
    print(f"  CE contracts: {len(ce_rows)}")
    print(f"  PE contracts: {len(pe_rows)}")
    print(f"  Futures (non-option): {len(fut_rows)}")
    print(f"  Unique future expiry dates: {expiry_dates[:10]}")
    if expiry_dates:
        print(f"  NEAREST FUTURE EXPIRY: {expiry_dates[0]}")

    # Sample future CE row
    if ce_rows:
        d, r = ce_rows[0]
        print(f"\n  Sample future CE row:")
        for k in ["pSymbolName","pTrdSymbol","dStrikePrice","lExpiryDate","pOptionType","pExchSeg","pSymbol"]:
            print(f"    {k}: {repr(r.get(k,'MISSING'))}")
        sp = r.get("dStrikePrice","0")
        try:
            print(f"    Strike (/100): {float(sp)/100:.0f}")
        except Exception:
            pass

    # ── Validation report ─────────────────────────────────────────────────────
    print(f"\n" + "=" * 60)
    print("VALIDATION REPORT")
    print("=" * 60)
    print(f"  SCRIP MASTER DOWNLOAD: SUCCESS")
    print(f"  CSV ROWS:              {len(rows)}")
    print(f"  NIFTY ROWS (exact):    {len(sym_exact)}")
    print(f"  NIFTY FUTURES:         {len(fut_rows)}")
    print(f"  NIFTY OPTIONS:         {len(ce_rows) + len(pe_rows)}")
    print(f"  FUTURE EXPIRIES:       {expiry_dates[:6]}")
    print(f"  NEAREST FUTURE EXPIRY: {expiry_dates[0] if expiry_dates else 'NONE'}")
    if future_rows:
        print(f"  CURRENT MASTER VALIDATION: PASS")
    else:
        print(f"  CURRENT MASTER VALIDATION: FAIL")
        print(f"  => Need to inspect lExpiryDate format and fix parser.")

if __name__ == "__main__":
    asyncio.run(main())
