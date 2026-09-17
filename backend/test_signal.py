import asyncio
import os
from datetime import datetime, timezone
from app.database.connection import AsyncSessionLocal
from app.services.telegram_listener import TelegramListenerService
from app.brokers.paper import PaperBroker

async def main():
    text = "BUY SENSEX 84000 CE ABOVE 200 SL 180 TARGET 300"
    paper_broker = PaperBroker()
    service = TelegramListenerService(paper_broker=paper_broker)
    
    async with AsyncSessionLocal() as session:
        res = await service.process_message(
            message_id=9999,
            channel_id=-1001234567,
            text=text,
            sender="Tester",
            received_at=datetime.now(timezone.utc),
            db_session=session
        )
        await session.commit()
        print("Process result:", res)

asyncio.run(main())
