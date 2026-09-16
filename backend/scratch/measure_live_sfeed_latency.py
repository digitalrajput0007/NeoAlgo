"""
Measures live SFeed tick latency for token 56980 over 25+ consecutive real ticks.
Captures monotonic clock timestamps at:
1. Kotak SFeed raw packet received
2. Binary decoder completed
3. KotakNeoFeed._on_message()
4. MarketDataService.update_tick()
5. TradeManager price listener invocation
"""
import asyncio
import time
import statistics
from datetime import datetime, timezone

from app.brokers.kotak_neo import KotakNeoBroker
from app.market_data.kotak_neo_feed import KotakNeoFeed, SFeedState
from app.services.market_data_service import market_data_service
from neo_api_client.websocket.feed import SFeedScrip

async def main():
    print("=== LIVE KOTAK SFEED LATENCY MEASUREMENT FOR TOKEN 56980 ===", flush=True)
    broker = KotakNeoBroker()
    auth_ok = await broker.authenticate()
    if not auth_ok:
        print(f"Authentication failed: {broker.auth_status}", flush=True)
        return

    feed = KotakNeoFeed(broker)
    
    samples = []
    
    # 5. TradeManager Listener probe
    listener_timestamps = {}
    def latency_listener(tok: str, ltp: float):
        t_listener = time.perf_counter_ns()
        listener_timestamps[tok] = t_listener

    market_data_service.register_listener(latency_listener)

    # Wrap _on_message to capture timestamps
    orig_on_message = feed._on_message
    
    def probed_on_message(message):
        t_decoder_done = time.perf_counter_ns()
        tok = str(getattr(message, "instrument_token", ""))
        
        if tok == "56980":
            ltp = float(getattr(message, "last_traded_price", 0.0))
            
            t_before_update = time.perf_counter_ns()
            # Calls market_data_service.update_tick which synchronously updates cache and calls listeners
            orig_on_message(message)
            t_after_update = time.perf_counter_ns()
            
            t_listener = listener_timestamps.get(tok, t_after_update)
            
            # Latency calculations in milliseconds
            decoder_to_cache_ms = (t_after_update - t_before_update) / 1_000_000.0
            tick_to_listener_ms = (t_listener - t_decoder_done) / 1_000_000.0
            total_processing_ms = (t_after_update - t_decoder_done) / 1_000_000.0
            
            samples.append({
                "tick_num": len(samples) + 1,
                "token": tok,
                "ltp": ltp,
                "cache_update_ms": decoder_to_cache_ms,
                "listener_ms": tick_to_listener_ms,
                "total_processing_ms": total_processing_ms,
                "iso_time": datetime.now(timezone.utc).isoformat()
            })
            print(f"[SFEED_LATENCY] #{len(samples):02d} | token={tok} | ltp={ltp:6.2f} | cache_update={decoder_to_cache_ms:6.4f}ms | listener={tick_to_listener_ms:6.4f}ms | total={total_processing_ms:6.4f}ms | time={samples[-1]['iso_time']}", flush=True)

    feed._on_message = probed_on_message

    conn_ok = await feed.connect()
    if not conn_ok:
        print("Failed to connect to SFeed WebSocket", flush=True)
        return

    sub_ok = await feed.subscribe_single("nse_fo", "56980")
    print(f"Subscribed 56980: {sub_ok}. Collecting 25 real ticks...", flush=True)

    start_wait = time.time()
    while len(samples) < 25 and (time.time() - start_wait) < 30:
        await asyncio.sleep(0.1)

    await feed.stop()

    if len(samples) < 20:
        print(f"Only collected {len(samples)} ticks. Retrying/timeout reached.", flush=True)
        return

    total_proc = [s["total_processing_ms"] for s in samples]
    cache_times = [s["cache_update_ms"] for s in samples]
    listener_times = [s["listener_ms"] for s in samples]

    print("\n==================================================", flush=True)
    print("SFEED LATENCY AUDIT REPORT (25 Real Kotak Ticks):", flush=True)
    print("==================================================", flush=True)
    print(f"AVERAGE_SFEED_PROCESSING_LATENCY_MS: {statistics.mean(total_proc):.4f} ms", flush=True)
    print(f"P95_SFEED_PROCESSING_LATENCY_MS:     {sorted(total_proc)[int(len(total_proc)*0.95)]:.4f} ms", flush=True)
    print(f"MAX_SFEED_PROCESSING_LATENCY_MS:     {max(total_proc):.4f} ms", flush=True)
    print(f"MIN_SFEED_PROCESSING_LATENCY_MS:     {min(total_proc):.4f} ms", flush=True)
    print(f"TICK_RECEIVED_TO_LATEST_LTP_UPDATE_MS: {statistics.mean(cache_times):.4f} ms", flush=True)
    print(f"TICK_TO_TRADEMANAGER_LATENCY_MS:       {statistics.mean(listener_times):.4f} ms", flush=True)

if __name__ == "__main__":
    asyncio.run(main())
