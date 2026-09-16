from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.orm import declarative_base
from app.config import settings

from sqlalchemy import event

from sqlalchemy.pool import NullPool

connect_args = {"timeout": 30.0} if "sqlite" in settings.database_url else {}
poolclass = NullPool if "sqlite" in settings.database_url else None

engine = create_async_engine(
    settings.database_url,
    poolclass=poolclass,
    connect_args=connect_args,
    echo=False,
)

if "sqlite" in settings.database_url:
    @event.listens_for(engine.sync_engine, "connect")
    def set_sqlite_pragma(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA busy_timeout=30000")
        cursor.close()

AsyncSessionLocal = async_sessionmaker(
    engine, class_=AsyncSession, expire_on_commit=False
)

Base = declarative_base()

async def get_db():
    async with AsyncSessionLocal() as session:
        try:
            yield session
        finally:
            await session.rollback()

async def init_db():
    from sqlalchemy.future import select
    from sqlalchemy import text
    from app.database import models
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        if "sqlite" in settings.database_url:
            for col, col_type in [
                ("username", "VARCHAR"),
                ("channel_type", "VARCHAR"),
                ("is_selected", "BOOLEAN DEFAULT 0")
            ]:
                try:
                    await conn.execute(text(f"ALTER TABLE telegram_channels ADD COLUMN {col} {col_type}"))
                except Exception:
                    pass
            try:
                await conn.execute(text("ALTER TABLE telegram_messages ADD COLUMN sender VARCHAR"))
            except Exception:
                pass
            for col, col_type in [
                ("paper_session_id", "VARCHAR"),
                ("paper_reset_at", "DATETIME")
            ]:
                try:
                    await conn.execute(text(f"ALTER TABLE broker_accounts ADD COLUMN {col} {col_type}"))
                except Exception:
                    pass
            for col, col_type in [
                ("daily_loss_protection_enabled", "BOOLEAN DEFAULT 1"),
                ("max_trades_protection_enabled", "BOOLEAN DEFAULT 1"),
                ("max_positions_protection_enabled", "BOOLEAN DEFAULT 1"),
                ("updated_at", "DATETIME")
            ]:
                try:
                    await conn.execute(text(f"ALTER TABLE trading_settings ADD COLUMN {col} {col_type}"))
                except Exception:
                    pass
            try:
                await conn.execute(text("ALTER TABLE trades ADD COLUMN risk_snapshot JSON"))
            except Exception:
                pass
            # Phase 10C: entry timeout columns
            try:
                await conn.execute(text("ALTER TABLE trading_settings ADD COLUMN entry_timeout_minutes INTEGER DEFAULT 15"))
            except Exception:
                pass
            for col, col_type in [
                ("entry_timeout_minutes", "INTEGER"),
                ("entry_expires_at", "DATETIME"),
                ("cancel_reason", "VARCHAR"),
            ]:
                try:
                    await conn.execute(text(f"ALTER TABLE trades ADD COLUMN {col} {col_type}"))
                except Exception:
                    pass
    
    async with AsyncSessionLocal() as session:
        stmt = select(models.User).where(models.User.id == 1)
        res = await session.execute(stmt)
        user = res.scalar_one_or_none()
        if not user:
            user = models.User(id=1, username="paper_trader", email="paper@trader.local", hashed_password="default_hash")
            session.add(user)
            await session.flush()
            
            broker = models.BrokerAccount(id=1, user_id=1, broker_name="PAPER", is_paper_trading=True)
            session.add(broker)
            
            trading_settings = models.TradingSettings(
                id=1,
                user_id=1,
                is_algo_active=True,
                max_daily_loss=5000.0,
                max_risk_per_trade=1000.0,
                max_trades_per_day=10,
                max_simultaneous_positions=3,
                partial_profit_percentage=50.0,
                trailing_stop_enabled=True,
                trailing_distance=5.0
            )
            session.add(trading_settings)
            await session.commit()
        else:
            await session.rollback()

