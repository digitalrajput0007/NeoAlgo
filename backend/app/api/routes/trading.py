from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List

from app.database.database import get_db
from app.brokers.paper import PaperBroker
from app.trading.trade_manager import TradeManager
from app.telegram.models import TradeSignal

router = APIRouter()

# In a real application, the broker instance would be a singleton or managed via DI
# For Phase 3, we instantiate one globally for the routes to share injected state.
global_paper_broker = PaperBroker()

class MarketPriceInject(BaseModel):
    instrument: str
    price: float

class MarketPriceResponse(BaseModel):
    instrument: str
    price: float
    affected_trades: List[dict]

@router.post("/test/market-price", response_model=MarketPriceResponse)
async def inject_market_price(req: MarketPriceInject, db: AsyncSession = Depends(get_db)):
    """Inject a simulated LTP and evaluate active trades."""
    global_paper_broker.inject_price(req.instrument, req.price)
    
    manager = TradeManager(db, global_paper_broker)
    affected = await manager.evaluate_market_prices(req.instrument, req.price)
    
    return MarketPriceResponse(
        instrument=req.instrument,
        price=req.price,
        affected_trades=affected
    )

class CreateTradeRequest(BaseModel):
    user_id: int
    broker_account_id: int
    signal: TradeSignal
    message_id: int

@router.post("/test/create-trade")
async def create_test_trade(req: CreateTradeRequest, db: AsyncSession = Depends(get_db)):
    """Inject a new signal to create a trade deterministically."""
    manager = TradeManager(db, global_paper_broker)
    trade = await manager.process_new_signal(
        user_id=req.user_id,
        broker_account_id=req.broker_account_id,
        signal_data=req.signal,
        message_id=req.message_id
    )
    return {"trade_id": trade.id, "status": trade.status}

@router.post("/pause")
async def pause_trading(db: AsyncSession = Depends(get_db)):
    from app.database.models import TradingSettings, AuditLog
    from sqlalchemy.future import select
    from datetime import datetime, timezone
    stmt = select(TradingSettings).where(TradingSettings.user_id == 1)
    settings = (await db.execute(stmt)).scalar_one_or_none()
    if not settings:
        settings = TradingSettings(user_id=1, new_trades_paused=True)
        db.add(settings)
    else:
        settings.new_trades_paused = True
    
    log = AuditLog(
        user_id=1,
        action="TRADING_PAUSED",
        details={"reason": "Manual pause"}
    )
    db.add(log)
    await db.commit()
    return {"status": "success", "new_trades_paused": True}

@router.post("/resume")
async def resume_trading(db: AsyncSession = Depends(get_db)):
    from app.database.models import TradingSettings, AuditLog
    from sqlalchemy.future import select
    stmt = select(TradingSettings).where(TradingSettings.user_id == 1)
    settings = (await db.execute(stmt)).scalar_one_or_none()
    if not settings:
        settings = TradingSettings(user_id=1, new_trades_paused=False)
        db.add(settings)
    else:
        settings.new_trades_paused = False
        
    log = AuditLog(
        user_id=1,
        action="TRADING_RESUMED",
        details={"reason": "Manual resume"}
    )
    db.add(log)
    await db.commit()
    return {"status": "success", "new_trades_paused": False}

@router.post("/cancel-waiting")
async def cancel_waiting_signals(db: AsyncSession = Depends(get_db)):
    manager = TradeManager(db, global_paper_broker)
    count = await manager.cancel_waiting_signals()
    return {"status": "success", "cancelled_count": count}

@router.post("/emergency-close")
async def emergency_close_all(db: AsyncSession = Depends(get_db)):
    from app.database.models import AuditLog
    log = AuditLog(user_id=1, action="EMERGENCY_CLOSE_ALL", details={"reason": "Manual trigger"})
    db.add(log)
    await db.flush() # flush to get an ID or just record it
    
    manager = TradeManager(db, global_paper_broker)
    result = await manager.emergency_close_all_paper_positions()
    return result

@router.get("/status")
async def get_trading_status(db: AsyncSession = Depends(get_db)):
    from app.database.models import TradingSettings, Trade, TradeState
    from sqlalchemy.future import select
    from sqlalchemy import func
    from datetime import datetime
    import pytz
    
    # Settings
    stmt_settings = select(TradingSettings).where(TradingSettings.user_id == 1)
    settings = (await db.execute(stmt_settings)).scalar_one_or_none()
    
    # Counts
    stmt_all = select(Trade).where(Trade.user_id == 1)
    trades = (await db.execute(stmt_all)).scalars().all()
    
    ist = pytz.timezone('Asia/Kolkata')
    now = datetime.now(ist)
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0).astimezone(pytz.utc).replace(tzinfo=None)
    
    daily_pnl = 0.0
    daily_trades = 0
    active_trades = 0
    open_positions = 0
    waiting_signals = 0
    partial_profit_positions = 0
    trailing_positions = 0
    
    for t in trades:
        if t.created_at >= today_start:
            daily_trades += 1
            daily_pnl += (t.realized_pnl or 0.0)
            
        if t.status in [TradeState.POSITION_OPEN, TradeState.PARTIAL_PROFIT, TradeState.TRAILING_STOP]:
            open_positions += 1
            active_trades += 1
        elif t.status == TradeState.WAITING_FOR_ENTRY:
            waiting_signals += 1
            active_trades += 1
            
        if t.status == TradeState.PARTIAL_PROFIT:
            partial_profit_positions += 1
        elif t.status == TradeState.TRAILING_STOP:
            trailing_positions += 1
            
    max_daily_loss = settings.max_daily_loss if settings else 6000
    daily_loss_limit_reached = daily_pnl <= -max_daily_loss if settings and settings.daily_loss_protection_enabled else False
    
    return {
        "session_date": now.strftime("%Y-%m-%d"),
        "mode": "PAPER",
        "daily_pnl": daily_pnl,
        "daily_trade_count": daily_trades,
        "active_trades": active_trades,
        "open_positions": open_positions,
        "waiting_signals": waiting_signals,
        "partial_profit_positions": partial_profit_positions,
        "trailing_positions": trailing_positions,
        "max_daily_loss": max_daily_loss,
        "daily_loss_limit_reached": daily_loss_limit_reached,
        "new_trades_paused": settings.new_trades_paused if settings else False
    }
