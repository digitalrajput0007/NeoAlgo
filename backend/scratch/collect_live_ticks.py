import asyncio
import httpx
import time

async def collect_ticks():
    prev_tick_count = -1
    ticks = []
    start_time = time.time()
    
    async with httpx.AsyncClient() as client:
        while len(ticks) < 12 and (time.time() - start_time) < 30:
            res = await client.get("http://127.0.0.1:8000/api/market-data/subscriptions")
            if res.status_code == 200:
                subs = res.json()
                sub_56980 = next((s for s in subs if s.get("instrument_token") == "56980"), None)
                if sub_56980:
                    tc = sub_56980.get("tick_count", 0)
                    ltp = sub_56980.get("latest_ltp")
                    ts = sub_56980.get("last_tick")
                    if tc != prev_tick_count:
                        ticks.append({
                            "tick_number": len(ticks) + 1,
                            "tick_count": tc,
                            "ltp": ltp,
                            "timestamp": ts
                        })
                        print(f"Collected tick #{len(ticks)}: count={tc}, ltp={ltp}, time={ts}")
                        prev_tick_count = tc
            await asyncio.sleep(0.5)

    print(f"\nSuccessfully collected {len(ticks)} live ticks for token 56980.")

if __name__ == "__main__":
    asyncio.run(collect_ticks())
