import asyncio
import sys
import os

sys.path.insert(0, os.path.abspath("."))

from sqlalchemy import select
from app.database.database import AsyncSessionLocal
from app.database.models import Trade, Order, Position, BrokerAccount, TradingSettings

async def inspect():
    async with AsyncSessionLocal() as session:
        # Get settings
        stmt_settings = select(TradingSettings)
        settings = (await session.execute(stmt_settings)).scalars().all()
        for s in settings:
            print(f"TradingSettings: user_id={s.user_id}, max_trades_per_day={s.max_trades_per_day}, max_simultaneous_positions={s.max_simultaneous_positions}, is_algo_active={s.is_algo_active}")

        # Get trades
        stmt_trades = select(Trade).order_by(Trade.id.asc())
        trades = (await session.execute(stmt_trades)).scalars().all()
        print(f"\nTotal trades in DB: {len(trades)}")
        
        for t in trades:
            # Check orders
            stmt_orders = select(Order).where(Order.trade_id == t.id)
            orders = (await session.execute(stmt_orders)).scalars().all()
            order_executed = len(orders) > 0

            # Check positions
            stmt_pos = select(Position).where(Position.trade_id == t.id)
            pos = (await session.execute(stmt_pos)).scalars().all()
            pos_opened = len(pos) > 0

            # Broker account
            stmt_broker = select(BrokerAccount).where(BrokerAccount.id == t.broker_account_id)
            broker = (await session.execute(stmt_broker)).scalar_one_or_none()
            broker_info = f"{broker.broker_name} (paper={broker.is_paper_trading})" if broker else "Unknown"

            print(f"Trade #{t.id} | Status: {t.status.value if hasattr(t.status, 'value') else t.status} | Instrument: {t.instrument_token} | Created: {t.created_at} | Broker: {broker_info} | Orders: {len(orders)} (executed={order_executed}) | Positions: {len(pos)} (opened={pos_opened})")

if __name__ == "__main__":
    asyncio.run(inspect())
