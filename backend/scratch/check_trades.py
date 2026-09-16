import asyncio
from app.database.database import AsyncSessionLocal
from app.database.models import Trade
from sqlalchemy.future import select

async def main():
    async with AsyncSessionLocal() as session:
        result = await session.execute(select(Trade))
        trades = result.scalars().all()
        print(f"Total trades: {len(trades)}")
        for t in trades:
            print(f"Trade #{t.id}: token={t.instrument_token}, status={t.status.value}, entry={t.entry_price}")

if __name__ == "__main__":
    asyncio.run(main())
