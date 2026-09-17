import asyncio
from app.market_data.kotak_neo_feed import get_sfeed_manager

async def main():
    s = get_sfeed_manager()
    print("State:", s.state)
    print("Connected:", s.is_connected)
    print("Feed Status:", s.feed_status)

if __name__ == "__main__":
    asyncio.run(main())
