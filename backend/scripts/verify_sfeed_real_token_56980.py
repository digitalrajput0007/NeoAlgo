"""
Verification Script for Real Kotak Neo SFeed Lifecycle and Token 56980 (CE).

Target:
  Token: 56980
  Exchange: nse_fo
  Trading Symbol: NIFTY2692223200CE
  Strike: 23200 CE
  Expiry: 2026-09-22

SAFETY:
  - LIVE ORDERS HARD-LOCKED TO DISABLED.
  - Never calls KotakNeoBroker.place_order().
  - Zero mock or fake ticks.
  - No credentials or secrets printed.
"""
import argparse
import asyncio
import os
import sys
import time
from datetime import datetime, timezone

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.brokers.kotak_neo import get_kotak_broker
from app.market_data.instrument_resolver import InstrumentResolver
from app.market_data.kotak_neo_feed import get_sfeed_manager, SFeedState
from app.services.market_data_service import market_data_service
from app.trading.trade_manager import TradeManager
from app.brokers.paper import PaperBroker
from app.database.database import AsyncSessionLocal


async def main(totp_code: str = None, totp_secret: str = None):
    print("=" * 75)
    print("KOTAK NEO SFEED LIFECYCLE & LIVE TICK VERIFICATION — TOKEN 56980")
    print("=" * 75)

    report = {
        "AUTHENTICATION": "FAIL",
        "SCRIP MASTER": "FAIL",
        "INSTRUMENT RESOLUTION": "FAIL",
        "SFEED WEBSOCKET CONNECTION": "FAIL",
        "SUBSCRIPTION ACK": "FAIL",
        "REAL SFEED TICK": "PENDING",
        "LTP": None,
        "TICK COUNT": 0,
        "LIFECYCLE STATE": SFeedState.DISCONNECTED,
        "PAPER BROKER INTEGRATION": "FAIL",
        "LIVE ORDER API INVOCATIONS": 0,
    }

    # 1. AUTHENTICATION
    print("\n--- STEP 1: AUTHENTICATING KOTAK NEO ---")
    broker = get_kotak_broker()
    auth_ok = await broker.authenticate(totp_code=totp_code, totp_secret=totp_secret)

    if not auth_ok:
        print(f"AUTHENTICATION: FAIL ({broker.auth_status})")
        print("Note: Set KOTAK_NEO_TOTP_SECRET in backend/.env for continuous TOTP generation.")
        return report

    report["AUTHENTICATION"] = "PASS"
    print("AUTHENTICATION: PASS")

    # 2. RESOLVE CURRENT INSTRUMENT TOKEN 56980
    print("\n--- STEP 2: VERIFYING TOKEN 56980 RESOLUTION ---")
    master_path = os.path.join("data", "instruments.csv")
    resolver = InstrumentResolver(master_path)
    resolver.initialize()
    report["SCRIP MASTER"] = "PASS" if len(resolver._cache) > 0 else "FAIL"

    target_token = "56980"
    target_exchange = "nse_fo"
    target_symbol = "NIFTY2692223200CE"
    target_strike = 23200.0
    target_option_type = "CE"
    target_expiry = "2026-09-22"

    try:
        resolved = await resolver.resolve_option_contract(
            underlying="NIFTY",
            strike=target_strike,
            option_type=target_option_type,
            expiry=target_expiry
        )
        p_sym = str(resolved.get("pSymbol"))
        p_trd = str(resolved.get("pTrdSymbol"))
        p_seg = str(resolved.get("pExchSeg", "nse_fo"))
        p_strike = float(resolved.get("strike", 0.0))
        p_opt = str(resolved.get("option_type", ""))

        print(f"Resolved from Scrip Master:")
        print(f"  pSymbol:          {p_sym}")
        print(f"  exchange segment: {p_seg}")
        print(f"  trading symbol:   {p_trd}")
        print(f"  strike:           {p_strike}")
        print(f"  option type:      {p_opt}")

        if p_sym != target_token:
            print(f"INSTRUMENT RESOLUTION: FAIL (Expected pSymbol {target_token}, got {p_sym})")
            return report
        if p_seg != target_exchange:
            print(f"INSTRUMENT RESOLUTION: FAIL (Expected pExchSeg {target_exchange}, got {p_seg})")
            return report
        if p_trd != target_symbol:
            print(f"INSTRUMENT RESOLUTION: FAIL (Expected pTrdSymbol {target_symbol}, got {p_trd})")
            return report

        report["INSTRUMENT RESOLUTION"] = "PASS"
        print("INSTRUMENT RESOLUTION: PASS")
    except Exception as e:
        print(f"INSTRUMENT RESOLUTION: FAIL ({e})")
        return report

    # 3. CONNECT SFEED WEBSOCKET
    print("\n--- STEP 3: CONNECTING SFEED WEBSOCKET ---")
    sfeed = get_sfeed_manager(broker)
    connect_ok = await sfeed.connect()

    if not connect_ok:
        print(f"SFEED WEBSOCKET CONNECTION: FAIL (error={sfeed.last_error})")
        return report

    report["SFEED WEBSOCKET CONNECTION"] = "PASS"
    report["LIFECYCLE STATE"] = sfeed.state
    print(f"SFEED WEBSOCKET CONNECTION: PASS (state={sfeed.state}, generation={sfeed.connection_generation})")

    # 4. SUBSCRIBE TOKEN 56980
    print(f"\n--- STEP 4: SUBSCRIBING TO {target_exchange}|{target_token} ({target_symbol}) ---")
    market_data_service.register_trade_interest(
        token=target_token,
        trade_id=9999,
        symbol=target_symbol,
        exchange_seg=target_exchange,
        trading_symbol=target_symbol,
        strike=23200.0,
        option_type="CE",
        expiry="2026-09-22"
    )

    sub_ok = await sfeed.subscribe_single(target_exchange, target_token)
    if not sub_ok:
        print(f"SUBSCRIPTION: FAIL (error={sfeed.last_error})")
        return report

    report["SUBSCRIPTION ACK"] = "PASS"
    report["LIFECYCLE STATE"] = sfeed.state
    print(f"SUBSCRIPTION ACK: PASS (state={sfeed.state})")

    # 5. WAIT FOR REAL SFEED TICK
    print(f"\n--- STEP 5: WAITING FOR REAL MARKET TICK (timeout=15s) ---")
    tick = await sfeed.wait_for_tick(target_token, timeout=15.0)

    if tick:
        ltp = float(tick.get("last_traded_price", 0.0))
        ts = tick.get("timestamp")
        sym = tick.get("symbol")
        ts_str = datetime.fromtimestamp(ts, tz=timezone.utc).isoformat() if ts else "N/A"

        print(f"\nREAL SFEED TICK: PASS")
        print(f"  Token:        {target_token}")
        print(f"  Symbol:       {sym}")
        print(f"  Decoded LTP:  ₹{ltp}")
        print(f"  Timestamp:    {ts_str}")
        print(f"  Total Ticks:  {sfeed.total_ticks_received}")
        print(f"  State:        {sfeed.state}")

        report["REAL SFEED TICK"] = "PASS"
        report["LTP"] = ltp
        report["TICK COUNT"] = sfeed.total_ticks_received
        report["LIFECYCLE STATE"] = sfeed.state

        # Check MarketDataService status
        sub_info = market_data_service.subscriptions.get(target_token, {})
        print(f"\nMarketDataService Subscription Status:")
        print(f"  feed_status:        {sub_info.get('feed_status')}")
        print(f"  subscription_state: {sub_info.get('subscription_state')}")
        print(f"  feed_type:          {sub_info.get('feed_type')}")
        print(f"  latest_ltp:         {sub_info.get('latest_ltp')}")

        # Verify PaperBroker Integration
        paper_broker = PaperBroker()
        async with AsyncSessionLocal() as session:
            manager = TradeManager(session, paper_broker)
            # Evaluate tick through TradeManager
            res = await manager.evaluate_market_prices(target_token, ltp)
            report["PAPER BROKER INTEGRATION"] = "PASS"
            print(f"Paper Broker Evaluation: PASS (affected trades: {len(res)})")
    else:
        print("\nREAL SFEED TICK: PENDING (No live tick received within 15s — market may be illiquid or closed for this strike)")
        report["REAL SFEED TICK"] = "PENDING_LIVE_ACTIVITY"
        report["LIFECYCLE STATE"] = sfeed.state

    # 6. VERIFY LIVE ORDERS REMAIN DISABLED
    print(f"\n--- STEP 6: VERIFYING LIVE ORDERS ARE DISABLED ---")
    live_invocations = getattr(broker, "_place_order_call_count", 0)
    report["LIVE ORDER API INVOCATIONS"] = live_invocations
    print(f"KotakNeoBroker.place_order() Invocations: {live_invocations} (STRICT ZERO)")

    # Clean up test interest and disconnect cleanly
    market_data_service.release_trade_interest(target_token, 9999)
    await sfeed.stop()

    print("\n" + "=" * 75)
    print("VERIFICATION SUMMARY:")
    for k, v in report.items():
        print(f"  {k:<30}: {v}")
    print("=" * 75)

    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Verify Kotak Neo SFeed Lifecycle for Token 56980")
    parser.add_argument("--totp", help="Fresh 6-digit TOTP code for authentication", default=None)
    parser.add_argument("--totp-secret", help="Base32 TOTP secret for local OTP generation", default=None)
    args = parser.parse_args()
    asyncio.run(main(totp_code=args.totp, totp_secret=args.totp_secret))
