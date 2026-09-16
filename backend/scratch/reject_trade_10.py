import asyncio
import sys
import os

sys.path.insert(0, os.path.abspath("."))

from sqlalchemy import select
from app.database.database import AsyncSessionLocal
from app.database.models import Trade, TradeState, AuditLog

async def reject_trade_10():
    async with AsyncSessionLocal() as session:
        stmt = select(Trade).where(Trade.id == 10)
        trade = (await session.execute(stmt)).scalar_one_or_none()
        if not trade:
            print("Trade #10 not found!")
            return
        
        print(f"Trade #10 before: status={trade.status}, instrument={trade.instrument_token}")
        trade.status = TradeState.REJECTED
        
        # Log audit event
        audit = AuditLog(
            user_id=trade.user_id,
            action="TRADE_REJECTED",
            details={
                "trade_id": trade.id,
                "reason": "INVALID_INSTRUMENT_PAPER_FALLBACK",
                "instrument_token": trade.instrument_token,
                "note": "Rejected due to incorrect paper instrument fallback. Clean rejection preserved for audit integrity."
            }
        )
        session.add(audit)
        await session.commit()
        print(f"Trade #10 after: status={trade.status}")

if __name__ == "__main__":
    asyncio.run(reject_trade_10())
