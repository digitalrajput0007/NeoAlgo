import logging
from typing import List, Optional
from datetime import datetime, timedelta, timezone
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

from app.database.database import get_db
from app.database.models import Trade, TradeEvent, TradeState, Signal

router = APIRouter()
logger = logging.getLogger(__name__)

@router.get("/trades")
async def get_trades(
    skip: int = 0,
    limit: int = 50,
    status: Optional[str] = None,
    underlying: Optional[str] = None,
    db: AsyncSession = Depends(get_db)
):
    stmt = select(Trade, Signal).outerjoin(Signal, Trade.signal_id == Signal.id).order_by(Trade.created_at.desc())
    
    if status:
        try:
            trade_state = TradeState(status)
            stmt = stmt.where(Trade.status == trade_state)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid status filter")
            
    # For now, simple like search on instrument token to roughly match underlying
    if underlying:
        stmt = stmt.where(Trade.instrument_token.ilike(f"%{underlying}%"))
        
    stmt = stmt.offset(skip).limit(limit)
    result = await db.execute(stmt)
    rows = result.all()
    
    trades = []
    for trade, sig in rows:
        trades.append({
            "id": trade.id,
            "instrument_token": trade.instrument_token,
            "instrument": f"{sig.underlying} {sig.strike} {sig.option_type}" if (sig and sig.underlying and sig.strike and sig.option_type) else trade.instrument_token,
            "entry_direction": getattr(trade, "entry_direction", None),
            "entry_price": trade.entry_price,
            "exit_price": trade.exit_price,
            "quantity": trade.quantity,
            "realized_pnl": trade.realized_pnl,
            "status": trade.status,
            "created_at": trade.created_at
        })
    
    # Also fetch total count for pagination
    count_stmt = select(func.count()).select_from(Trade)
    if status:
        count_stmt = count_stmt.where(Trade.status == TradeState(status))
    if underlying:
        count_stmt = count_stmt.where(Trade.instrument_token.ilike(f"%{underlying}%"))
    count_res = await db.execute(count_stmt)
    total_count = count_res.scalar()
    
    return {
        "items": trades,
        "total": total_count,
        "skip": skip,
        "limit": limit
    }

@router.get("/trades/{trade_id}")
async def get_trade(
    trade_id: int,
    db: AsyncSession = Depends(get_db)
):
    stmt = select(Trade).where(Trade.id == trade_id)
    result = await db.execute(stmt)
    trade = result.scalar_one_or_none()
    if not trade:
        raise HTTPException(status_code=404, detail="Trade not found")
    return trade

@router.get("/trades/{trade_id}/events")
async def get_trade_events(
    trade_id: int,
    db: AsyncSession = Depends(get_db)
):
    stmt = select(TradeEvent).where(TradeEvent.trade_id == trade_id).order_by(TradeEvent.created_at.desc())
    events_res = await db.execute(stmt)
    events = events_res.scalars().all()
    return events

@router.get("/analytics")
async def get_analytics(
    days: int = 30,
    db: AsyncSession = Depends(get_db)
):
    since = datetime.now(timezone.utc) - timedelta(days=days)
    stmt = select(Trade).where(
        Trade.status == TradeState.CLOSED,
        Trade.created_at >= since
    )
    result = await db.execute(stmt)
    closed_trades = result.scalars().all()
    
    total_trades = len(closed_trades)
    winning_trades = len([t for t in closed_trades if (t.realized_pnl or 0) > 0])
    losing_trades = len([t for t in closed_trades if (t.realized_pnl or 0) <= 0])
    total_pnl = sum([t.realized_pnl or 0 for t in closed_trades])
    win_rate = (winning_trades / total_trades * 100) if total_trades > 0 else 0
    
    return {
        "period_days": days,
        "total_closed_trades": total_trades,
        "winning_trades": winning_trades,
        "losing_trades": losing_trades,
        "win_rate_percentage": win_rate,
        "total_realized_pnl": total_pnl
    }

@router.get("/analytics/daily")
async def get_daily_analytics(
    days: int = 30,
    db: AsyncSession = Depends(get_db)
):
    since = datetime.now(timezone.utc) - timedelta(days=days)
    stmt = select(Trade).where(
        Trade.status == TradeState.CLOSED,
        Trade.created_at >= since
    )
    result = await db.execute(stmt)
    closed_trades = result.scalars().all()
    
    daily_pnl = {}
    for t in closed_trades:
        # Group by the day it was created or closed? Usually closed date makes sense for PnL
        exit_date = t.exit_triggered_at or t.updated_at
        if exit_date:
            date_str = exit_date.strftime("%Y-%m-%d")
            daily_pnl[date_str] = daily_pnl.get(date_str, 0) + (t.realized_pnl or 0)
            
    # Sort by date
    sorted_daily = [{"date": k, "pnl": v} for k, v in sorted(daily_pnl.items())]
    
    return sorted_daily
