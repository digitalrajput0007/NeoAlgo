import asyncio
from app.market_data.instrument_resolver import InstrumentResolver

async def test():
    r = InstrumentResolver()
    r.initialize()
    
    try:
        res = await r.resolve_option_contract('SENSEX', 84000.0, 'CE', None)
        print(res)
    except Exception as e:
        print(f"Error: {e}")

asyncio.run(test())
