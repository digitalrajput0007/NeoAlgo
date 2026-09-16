import asyncio
import sys
import os
import json

sys.path.insert(0, os.path.abspath("."))

from sqlalchemy import select
from app.database.database import AsyncSessionLocal
from app.database.models import Trade, TradeState, AuditLog
from app.api.routes.dashboard import get_trade_lifecycle

async def check_lifecycle():
    async with AsyncSessionLocal() as session:
        res = await get_trade_lifecycle(10, session)
        print("Trade #10 Lifecycle:")
        print(f"Status: {res['trade']['status']}")
        print(f"Instrument: {res['trade']['instrument']}")
        print("\nTimeline Steps:")
        for step in res["timeline"]:
            print(f"Step {step['step']}: {step['title']} | Completed: {step['completed']} | Details: {step['details']}")

if __name__ == "__main__":
    asyncio.run(check_lifecycle())
