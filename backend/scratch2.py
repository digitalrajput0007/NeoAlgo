import asyncio
from app.market_data.instrument_resolver import InstrumentResolver

async def main():
    resolver = InstrumentResolver()
    resolver.initialize()
    
    for symbol in ["NIFTY 50", "BANK NIFTY", "SENSEX", "INDIA VIX"]:
        try:
            res = await resolver.resolve_index(symbol)
            print(f"Resolved {symbol}: {res}")
        except Exception as e:
            print(f"Error for {symbol}: {e}")

if __name__ == "__main__":
    asyncio.run(main())
