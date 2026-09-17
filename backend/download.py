import asyncio
from app.brokers.kotak_neo import KotakNeoBroker
from app.database.connection import SessionLocal
from app.database.models import BrokerAccount

async def main():
    db = SessionLocal()
    acc = db.query(BrokerAccount).first()
    db.close()
    broker = KotakNeoBroker(acc.credentials)
    await broker.authenticate()
    await broker.download_scrip_master('data/instruments.csv')

asyncio.run(main())
