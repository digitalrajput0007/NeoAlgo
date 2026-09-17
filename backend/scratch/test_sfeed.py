import asyncio
import logging
from app.brokers.kotak_neo import get_kotak_broker
from app.market_data.kotak_neo_feed import get_sfeed_manager

logging.basicConfig(level=logging.DEBUG)

async def main():
    broker = get_kotak_broker()
    await broker.authenticate()
    
    sfeed = get_sfeed_manager()
    sfeed.broker = broker
    
    print("Connecting sfeed...")
    task = asyncio.create_task(sfeed.run_supervisor())
    await asyncio.sleep(5)
    print("State:", sfeed.state)
    print("Connected:", sfeed.is_connected)
    sfeed._stop_event.set()

if __name__ == "__main__":
    asyncio.run(main())
