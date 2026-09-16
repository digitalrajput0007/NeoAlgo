import uuid
from datetime import datetime, timezone
from typing import List, Optional, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.future import select
from sqlalchemy import func
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.database import get_db, AsyncSessionLocal
from app.database.models import (
    Trade, TradeState, Signal, Order, Position, AuditLog,
    TradingSettings, TelegramMessage, RiskEvent, User, BrokerAccount,
    TelegramChannel
)
from app.services.market_data_service import market_data_service
from app.services.telegram_listener import telegram_listener
from app.brokers.kotak_neo import KotakNeoBroker, get_kotak_broker
from app.market_data.kotak_neo_feed import get_sfeed_manager
from app.trading.trade_manager import TradeManager
import time
from app.config import settings
from app.utils.timezone import to_utc_iso

router = APIRouter()

# Global read-only Kotak broker instance
kotak_broker = get_kotak_broker()

# In-memory caches to eliminate expensive repetitive network and CPU operations
_profile_cache = {"data": None, "timestamp": 0.0}
PROFILE_CACHE_TTL_SECONDS = 300.0  # 5 minutes

_scrip_count_cache = {"scrip_count": 0, "nifty_count": 0, "cache_id": None}

# Ensure market data service price listener updates active trades
async def _handle_price_tick(token: str, ltp: float):
    async with AsyncSessionLocal() as session:
        manager = TradeManager(session, telegram_listener.paper_broker)
        await manager.evaluate_market_prices(token, ltp)

market_data_service.register_listener(_handle_price_tick)


# =========================================================================
# 1. DASHBOARD OVERVIEW SUMMARY
# =========================================================================
@router.get("/dashboard/summary")
async def get_dashboard_summary(db: AsyncSession = Depends(get_db)):
    """
    Returns high-level status for the dashboard overview.
    No hardcoded dummy data — 0 if no records exist.
    """
    # 1. Counts and metrics
    now_utc = datetime.now(timezone.utc)
    today_start = now_utc.replace(hour=0, minute=0, second=0, microsecond=0)

    # Determine Current Paper Session Boundary
    stmt_broker = select(BrokerAccount).where(BrokerAccount.is_paper_trading == True).limit(1)
    paper_broker_acc = (await db.execute(stmt_broker)).scalar_one_or_none()

    session_start = None
    session_id = None
    if paper_broker_acc:
        session_start = paper_broker_acc.paper_reset_at
        session_id = paper_broker_acc.paper_session_id

    # Fallback to latest PAPER_STATE_RESET in AuditLog if broker account timestamp is None
    if not session_start:
        stmt_last_reset = (
            select(AuditLog)
            .where(AuditLog.action == "PAPER_STATE_RESET")
            .order_by(AuditLog.id.desc())
            .limit(1)
        )
        last_reset = (await db.execute(stmt_last_reset)).scalar_one_or_none()
        if last_reset:
            session_start = last_reset.created_at
            if isinstance(last_reset.details, dict):
                session_id = last_reset.details.get("new_session_identifier") or last_reset.details.get("session_id")

    # Active Trades & P&L (Consolidated into 1 query)
    active_states = [TradeState.WAITING_FOR_ENTRY, TradeState.ENTRY_TRIGGERED, TradeState.POSITION_OPEN, TradeState.PARTIAL_PROFIT, TradeState.TRAILING_STOP]
    trade_time = func.coalesce(Trade.updated_at, Trade.created_at)
    if session_start:
        stmt_trades = select(
            func.count(Trade.id).filter(Trade.status.in_(active_states)),
            func.sum(Trade.realized_pnl).filter(trade_time >= session_start),
            func.sum(Trade.realized_pnl).filter(trade_time >= today_start)
        )
    else:
        stmt_trades = select(
            func.count(Trade.id).filter(Trade.status.in_(active_states)),
            func.sum(Trade.realized_pnl).filter(trade_time >= today_start),
            func.sum(Trade.realized_pnl).filter(trade_time >= today_start)
        )
    trades_res = (await db.execute(stmt_trades)).one_or_none()
    active_trades = int(trades_res[0]) if trades_res and trades_res[0] is not None else 0
    current_session_pnl = float(trades_res[1] or 0.0) if trades_res else 0.0
    historical_today_pnl = float(trades_res[2] or 0.0) if trades_res else 0.0

    # Open Positions
    stmt_pos = select(func.count(Position.id)).where(Position.is_open == True)
    open_positions = (await db.execute(stmt_pos)).scalar() or 0

    # Orders (Consolidated session & historical into 1 query)
    if session_start:
        stmt_orders = select(
            func.count(Order.id).filter(Order.created_at >= session_start),
            func.count(Order.id).filter(Order.created_at >= today_start)
        )
    else:
        stmt_orders = select(
            func.count(Order.id).filter(Order.created_at >= today_start),
            func.count(Order.id).filter(Order.created_at >= today_start)
        )
    orders_res = (await db.execute(stmt_orders)).one_or_none()
    current_session_orders = int(orders_res[0]) if orders_res and orders_res[0] is not None else 0
    historical_orders_today = int(orders_res[1]) if orders_res and orders_res[1] is not None else 0

    # Signals (Consolidated session & historical into 1 query)
    if session_start:
        stmt_signals = select(
            func.count(Signal.id).filter(Signal.created_at >= session_start),
            func.count(Signal.id).filter(Signal.created_at >= today_start)
        )
    else:
        stmt_signals = select(
            func.count(Signal.id).filter(Signal.created_at >= today_start),
            func.count(Signal.id).filter(Signal.created_at >= today_start)
        )
    signals_res = (await db.execute(stmt_signals)).one_or_none()
    current_session_signals = int(signals_res[0]) if signals_res and signals_res[0] is not None else 0
    signals_today = int(signals_res[1]) if signals_res and signals_res[1] is not None else 0

    # 2. Connection states
    tel_status = await telegram_listener.get_status()
    kotak_connected = kotak_broker.auth_status == "CONNECTED"
    sfeed_status = market_data_service.get_status()

    # DB connectivity verified from successful queries above
    db_connected = True

    sel_ch = tel_status.get("selected_channel")
    channel_display = f"{sel_ch['channel_name']}" if sel_ch else "NONE"

    return {
        "mode": "PAPER",
        "live_orders": "DISABLED",
        "connections": {
            "telegram": {
                "status": tel_status.get("listener_status", "DISCONNECTED"),
                "channel": channel_display,
                "messages_received": tel_status.get("messages_received", 0)
            },
            "kotak": {
                "status": kotak_broker.auth_status,
                "read_only": True,
                "last_request": kotak_broker.last_successful_request
            },
            "sfeed": {
                "status": sfeed_status["feed_status"],
                "active_subscriptions": sfeed_status["active_subscriptions"],
                "total_ticks": sfeed_status["total_ticks"],
                "last_tick_time": sfeed_status["last_tick_time"]
            },
            "database": {
                "status": "CONNECTED" if db_connected else "DISCONNECTED",
                "type": "SQLite / PostgreSQL"
            }
        },
        "metrics": {
            "today_pnl": float(current_session_pnl),
            "current_session_pnl": float(current_session_pnl),
            "historical_today_pnl": float(historical_today_pnl),
            "active_trades": int(active_trades),
            "open_positions": int(open_positions),
            "signals_today": int(signals_today),
            "current_session_signals": int(current_session_signals),
            "orders_today": int(current_session_orders),
            "current_session_orders": int(current_session_orders),
            "historical_orders_today": int(historical_orders_today),
            "paper_session_id": session_id,
            "paper_reset_at": to_utc_iso(session_start)
        }
    }


# =========================================================================
# 2. TELEGRAM STATUS, CHANNELS, AUTH & MESSAGES
# =========================================================================
class SelectChannelRequest(BaseModel):
    channel_id: str
    channel_name: Optional[str] = None

class TelegramSendCodeRequest(BaseModel):
    phone: str

class TelegramSignInRequest(BaseModel):
    phone: str
    code: str
    password: Optional[str] = None

@router.get("/telegram/status")
async def get_telegram_status():
    """Sanitized Telegram status — NO credentials, api_hash, or secret tokens."""
    return await telegram_listener.get_status()

@router.post("/telegram/connect")
async def connect_telegram():
    """Idempotently starts the Telegram listener."""
    if not telegram_listener.is_running:
        await telegram_listener.start()
    return await telegram_listener.get_status()

@router.post("/telegram/disconnect")
async def disconnect_telegram():
    """Idempotently stops the Telegram listener."""
    if telegram_listener.is_running:
        await telegram_listener.stop()
    return await telegram_listener.get_status()

@router.post("/telegram/reconnect")
async def reconnect_telegram():
    """Stops and restarts the Telegram listener."""
    if telegram_listener.is_running:
        await telegram_listener.stop()
    await telegram_listener.start()
    return await telegram_listener.get_status()

@router.get("/telegram/channels")
async def get_telegram_channels():
    """Discovers accessible Telegram dialogs/channels for the authenticated user account."""
    return await telegram_listener.discover_channels()

@router.post("/telegram/channels/select")
async def select_telegram_channel(req: SelectChannelRequest):
    """Selects the active channel for signal listening and persists to DB."""
    return await telegram_listener.select_channel(req.channel_id, req.channel_name)

@router.post("/telegram/auth/send-code")
async def telegram_auth_send_code(req: TelegramSendCodeRequest):
    """Sends login code to Telegram Account B."""
    try:
        return await telegram_listener.send_login_code(req.phone)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.post("/telegram/auth/sign-in")
async def telegram_auth_sign_in(req: TelegramSignInRequest):
    """Signs in Telegram Account B with received code and optional 2FA password."""
    try:
        return await telegram_listener.sign_in_with_code(req.phone, req.code, req.password)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.post("/telegram/auth/logout")
async def telegram_auth_logout():
    """Logs out Telegram Account B."""
    return await telegram_listener.logout()

@router.get("/telegram/messages")
async def get_telegram_messages(limit: int = 50, db: AsyncSession = Depends(get_db)):
    """List of persisted Telegram messages."""
    stmt = (
        select(TelegramMessage, TelegramChannel.channel_name)
        .outerjoin(TelegramChannel, TelegramMessage.channel_id == TelegramChannel.channel_id)
        .order_by(TelegramMessage.id.desc())
        .limit(limit)
    )
    res = await db.execute(stmt)
    rows = res.all()
    
    return [
        {
            "id": m.id,
            "telegram_message_id": m.telegram_message_id,
            "channel_id": channel_name or m.channel_id,
            "sender": m.sender,
            "received_at": to_utc_iso(m.received_at),
            "message_text": m.message_text,
            "message_type": m.message_type,
            "parsed_successfully": m.parsed_successfully,
            "trade_id": m.trade_id,
            "processing_status": m.processing_status,
            "error_message": m.error_message
        }
        for m, channel_name in rows
    ]


# =========================================================================
# 3. SIGNALS & LIFECYCLE
# =========================================================================
@router.get("/signals")
async def get_signals(limit: int = 50, db: AsyncSession = Depends(get_db)):
    """List of parsed trading signals."""
    stmt = (
        select(Signal, Trade.status.label("trade_status"), Trade.id.label("trade_id"))
        .outerjoin(Trade, Trade.signal_id == Signal.id)
        .order_by(Signal.id.desc())
        .limit(limit)
    )
    res = await db.execute(stmt)
    rows = res.all()
    
    signals = []
    for sig, trade_status, trade_id in rows:
        signals.append({
            "id": sig.id,
            "timestamp": to_utc_iso(sig.created_at),
            "underlying": sig.underlying,
            "strike": sig.strike,
            "option_type": sig.option_type,
            "expiry": sig.expiry,
            "entry_trigger": sig.entry_trigger,
            "stop_loss": sig.stop_loss,
            "target": sig.target,
            "telegram_cmp": sig.telegram_cmp,
            "parser_status": "VALID",
            "trade_state": trade_status.value if trade_status else "NO_TRADE",
            "trade_id": trade_id
        })
    return signals

@router.get("/signals/{signal_id}")
async def get_signal_detail(signal_id: int, db: AsyncSession = Depends(get_db)):
    """Detailed signal information with linked trade."""
    stmt = select(Signal).where(Signal.id == signal_id)
    sig = (await db.execute(stmt)).scalar_one_or_none()
    if not sig:
        raise HTTPException(status_code=404, detail="Signal not found")
        
    t_stmt = select(Trade).where(Trade.signal_id == signal_id)
    trade = (await db.execute(t_stmt)).scalar_one_or_none()

    return {
        "signal": {
            "id": sig.id,
            "underlying": sig.underlying,
            "strike": sig.strike,
            "option_type": sig.option_type,
            "expiry": sig.expiry,
            "entry_trigger": sig.entry_trigger,
            "stop_loss": sig.stop_loss,
            "target": sig.target,
            "telegram_cmp": sig.telegram_cmp,
            "created_at": to_utc_iso(sig.created_at),
        },
        "trade_id": trade.id if trade else None,
        "trade_status": trade.status.value if trade else None
    }


# =========================================================================
# 4. TRADES & DETAILED LIFECYCLE TIMELINE
# =========================================================================
@router.get("/trades")
async def get_trades(
    scope: Optional[str] = Query(None, description="Scope filter: 'active' (default), 'history', or 'all'"),
    limit: int = 50,
    db: AsyncSession = Depends(get_db)
):
    """List of trades with scope filtering ('active' default, 'history', or 'all')."""
    active_states = [
        TradeState.WAITING_FOR_ENTRY,
        TradeState.ENTRY_TRIGGERED,
        TradeState.ENTRY_ORDER_PENDING,
        TradeState.POSITION_OPEN,
        TradeState.PARTIAL_PROFIT,
        TradeState.TRAILING_STOP
    ]

    stmt = select(Trade, Signal).outerjoin(Signal, Trade.signal_id == Signal.id).order_by(Trade.id.desc())

    if scope == "history":
        stmt = stmt.where(~Trade.status.in_(active_states))
    elif scope == "all":
        pass  # return all trades
    else:  # Default: active trades only
        stmt = stmt.where(Trade.status.in_(active_states))

    stmt = stmt.limit(limit)
    res = await db.execute(stmt)
    rows = res.all()
    
    trades = []
    for trade, sig in rows:
        # Get live LTP from market data service
        sub = market_data_service.subscriptions.get(trade.instrument_token or "")
        current_ltp = sub.get("latest_ltp") if sub else None
        
        trades.append({
            "id": trade.id,
            "signal_id": sig.id if sig else None,
            "instrument": trade.instrument_token,
            "underlying": sig.underlying if sig else None,
            "strike": sig.strike if sig else None,
            "option_type": sig.option_type if sig else None,
            "expiry": sig.expiry if sig else None,
            "entry_trigger": sig.entry_trigger if sig else None,
            "actual_entry": trade.entry_price,
            "current_ltp": current_ltp,
            "stop_loss": sig.stop_loss if sig else None,
            "target": sig.target if sig else None,
            "quantity": trade.quantity,
            "realized_pnl": trade.realized_pnl,
            "status": trade.status.value,
            "cancel_reason": getattr(trade, "cancel_reason", None),
            "entry_timeout_minutes": getattr(trade, "entry_timeout_minutes", None),
            "entry_expires_at": to_utc_iso(getattr(trade, "entry_expires_at", None)),
            "created_at": to_utc_iso(trade.created_at),
            "updated_at": to_utc_iso(trade.updated_at)
        })
    return trades

@router.get("/trades/{trade_id}")
async def get_trade_lifecycle(trade_id: int, db: AsyncSession = Depends(get_db)):
    """
    Complete 10-step lifecycle timeline for debugging and transparency:
    1. Telegram Received
    2. Signal Parsed
    3. Instrument Resolved
    4. SFeed Subscribed
    5. LTP Updates
    6. Entry Triggered
    7. Paper Order Placed
    8. Position Open
    9. SL/Target Monitoring
    10. Exit
    """
    stmt = select(Trade).where(Trade.id == trade_id)
    trade = (await db.execute(stmt)).scalar_one_or_none()
    if not trade:
        raise HTTPException(status_code=404, detail="Trade not found")
        
    sig_stmt = select(Signal).where(Signal.id == trade.signal_id)
    sig = (await db.execute(sig_stmt)).scalar_one_or_none()
    
    # Associated Telegram Message
    msg = None
    if sig and sig.message_id:
        try:
            m_id = int(sig.message_id)
            m_stmt = select(TelegramMessage).where(TelegramMessage.id == m_id)
            msg = (await db.execute(m_stmt)).scalar_one_or_none()
        except (ValueError, TypeError):
            pass

    # Orders for this trade
    ord_stmt = select(Order).where(Order.trade_id == trade_id).order_by(Order.id.asc())
    orders = (await db.execute(ord_stmt)).scalars().all()

    # Position
    pos_stmt = select(Position).where(Position.trade_id == trade_id)
    pos = (await db.execute(pos_stmt)).scalar_one_or_none()

    # Audit Logs
    audit_stmt = select(AuditLog).order_by(AuditLog.id.asc())
    all_logs = (await db.execute(audit_stmt)).scalars().all()
    trade_logs = [log for log in all_logs if (log.details or {}).get("trade_id") == trade_id]

    # Market Data
    sub = market_data_service.subscriptions.get(trade.instrument_token or "")
    current_ltp = sub.get("latest_ltp") if sub else None

    # Construct the 10-step timeline
    timeline = [
        {
            "step": 1,
            "title": "Telegram Received",
            "completed": msg is not None,
            "timestamp": to_utc_iso(msg.received_at) if msg and msg.received_at else to_utc_iso(trade.created_at),
            "details": {
                "channel_id": msg.channel_id if msg else "N/A",
                "message_id": msg.telegram_message_id if msg else "N/A",
                "raw_text": msg.message_text if msg else "N/A"
            }
        },
        {
            "step": 2,
            "title": "Signal Parsed",
            "completed": sig is not None,
            "timestamp": to_utc_iso(sig.created_at) if sig and sig.created_at else None,
            "details": {
                "underlying": sig.underlying if sig else None,
                "strike": sig.strike if sig else None,
                "option_type": sig.option_type if sig else None,
                "entry_trigger": sig.entry_trigger if sig else None,
                "stop_loss": sig.stop_loss if sig else None,
                "target": sig.target if sig else None,
                "telegram_cmp": sig.telegram_cmp if sig else None,
                "cmp_note": "CMP is informational only and does NOT trigger order."
            }
        },
        {
            "step": 3,
            "title": "Instrument Resolved",
            "completed": trade.instrument_token is not None,
            "timestamp": to_utc_iso(trade.created_at),
            "details": {
                "instrument_token": trade.instrument_token,
                "symbol": sub.get("pSymbol") if sub else trade.instrument_token,
                "trading_symbol": sub.get("pTrdSymbol") if sub else trade.instrument_token
            }
        },
        {
            "step": 4,
            "title": "SFeed Subscribed",
            "completed": sub is not None and sub.get("feed_status") == "SUBSCRIBED" and not trade.instrument_token.startswith("PAPER_"),
            "timestamp": to_utc_iso(sub.get("last_tick")) if (sub and not trade.instrument_token.startswith("PAPER_")) else None,
            "details": {
                "feed_type": sub.get("feed_type") if (sub and not trade.instrument_token.startswith("PAPER_")) else "NOT EXECUTED",
                "feed_status": sub.get("feed_status") if (sub and not trade.instrument_token.startswith("PAPER_")) else "NOT EXECUTED"
            }
        },
        {
            "step": 5,
            "title": "LTP Updates",
            "completed": current_ltp is not None and not trade.instrument_token.startswith("PAPER_"),
            "timestamp": to_utc_iso(sub.get("last_tick")) if (sub and not trade.instrument_token.startswith("PAPER_")) else None,
            "details": {
                "latest_ltp": current_ltp if (current_ltp is not None and not trade.instrument_token.startswith("PAPER_")) else "NOT EXECUTED",
                "feed_source": sub.get("feed_type") if (sub and current_ltp is not None and not trade.instrument_token.startswith("PAPER_")) else "NOT EXECUTED"
            }
        },
        {
            "step": 6,
            "title": "Entry Triggered",
            "completed": trade.status not in [TradeState.NEW_SIGNAL, TradeState.WAITING_FOR_ENTRY, TradeState.REJECTED],
            "timestamp": next((to_utc_iso(l.created_at) for l in trade_logs if "ENTRY" in l.action or "ORDER_CREATED" in l.action), None),
            "details": {
                "entry_trigger_level": sig.entry_trigger if (sig and trade.status not in [TradeState.NEW_SIGNAL, TradeState.WAITING_FOR_ENTRY, TradeState.REJECTED]) else "NOT EXECUTED",
                "triggered_price": (trade.entry_price or current_ltp) if trade.status not in [TradeState.NEW_SIGNAL, TradeState.WAITING_FOR_ENTRY, TradeState.REJECTED] else "NOT EXECUTED"
            }
        },
        {
            "step": 7,
            "title": "Paper Order Placed",
            "completed": len(orders) > 0,
            "timestamp": to_utc_iso(orders[0].created_at) if orders else None,
            "details": {
                "orders_count": len(orders),
                "orders": [{"id": o.broker_order_id, "type": o.order_type, "qty": o.quantity, "price": o.price, "status": o.status} for o in orders]
            } if len(orders) > 0 else {"status": "NOT EXECUTED"}
        },
        {
            "step": 8,
            "title": "Position Open",
            "completed": trade.status in [TradeState.POSITION_OPEN, TradeState.PARTIAL_PROFIT, TradeState.TRAILING_STOP, TradeState.CLOSED] and (pos is not None),
            "timestamp": to_utc_iso(pos.created_at) if pos and pos.created_at else None,
            "details": {
                "is_open": pos.is_open if pos else False,
                "quantity": pos.quantity if pos else 0,
                "average_price": pos.average_price if pos else trade.entry_price
            } if pos is not None else {"status": "NOT EXECUTED"}
        },
        {
            "step": 9,
            "title": "SL / Target Monitoring",
            "completed": trade.status in [TradeState.POSITION_OPEN, TradeState.PARTIAL_PROFIT, TradeState.TRAILING_STOP, TradeState.CLOSED],
            "timestamp": None,
            "details": {
                "stop_loss": sig.stop_loss if sig else None,
                "target": sig.target if sig else None,
                "current_ltp": current_ltp,
                "state": trade.status.value
            } if trade.status in [TradeState.POSITION_OPEN, TradeState.PARTIAL_PROFIT, TradeState.TRAILING_STOP, TradeState.CLOSED] else {"status": "NOT EXECUTED"}
        },
        {
            "step": 10,
            "title": "Exit",
            "completed": trade.status == TradeState.CLOSED,
            "timestamp": to_utc_iso(trade.updated_at) if trade.status == TradeState.CLOSED and trade.updated_at else None,
            "details": {
                "status": trade.status.value,
                "exit_price": trade.exit_price,
                "realized_pnl": trade.realized_pnl
            } if trade.status == TradeState.CLOSED else {"status": "NOT EXECUTED"}
        }
    ]

    return {
        "trade": {
            "id": trade.id,
            "signal_id": trade.signal_id,
            "status": trade.status.value,
            "instrument_token": trade.instrument_token,
            "entry_price": trade.entry_price,
            "exit_price": trade.exit_price,
            "quantity": trade.quantity,
            "realized_pnl": trade.realized_pnl,
            "current_ltp": current_ltp,
            "cancel_reason": trade.cancel_reason,
            "entry_tolerance": getattr(trade, "entry_tolerance", None),
            "entry_direction": getattr(trade, "entry_direction", None),
            "entry_lower_bound": getattr(trade, "entry_lower_bound", None),
            "entry_upper_bound": getattr(trade, "entry_upper_bound", None),
            "actual_trigger_ltp": getattr(trade, "actual_trigger_ltp", None),
            "actual_triggered_at": to_utc_iso(getattr(trade, "actual_triggered_at", None)),
            "partial_profit_taken": getattr(trade, "partial_profit_taken", False),
            "trailing_active": getattr(trade, "trailing_active", False),
            "highest_ltp": getattr(trade, "highest_ltp", None),
            "trailing_stop": getattr(trade, "trailing_stop", None),
            "created_at": to_utc_iso(trade.created_at),
            "updated_at": to_utc_iso(trade.updated_at)
        },
        "signal": {
            "id": sig.id if sig else None,
            "underlying": sig.underlying if sig else None,
            "strike": sig.strike if sig else None,
            "option_type": sig.option_type if sig else None,
            "expiry": sig.expiry if sig else None,
            "entry_trigger": sig.entry_trigger if sig else None,
            "stop_loss": sig.stop_loss if sig else None,
            "target": sig.target if sig else None,
            "telegram_cmp": sig.telegram_cmp if sig else None,
            "created_at": to_utc_iso(sig.created_at) if sig else None,
        },
        "timeline": timeline,
        "logs": [{"id": l.id, "action": l.action, "details": l.details, "timestamp": to_utc_iso(l.created_at)} for l in trade_logs]
    }


# =========================================================================
# 5. POSITIONS & ORDERS
# =========================================================================
@router.get("/positions")
async def get_positions(
    scope: Optional[str] = Query(None, description="Scope filter: 'open' (default), 'history', or 'all'"),
    db: AsyncSession = Depends(get_db)
):
    """
    List of positions with scope filtering.
    - Default or scope='open': Returns strictly open positions (is_open == True).
    - scope='history': Returns closed / reset positions (is_open == False).
    - scope='all': Returns all positions.
    """
    stmt = select(Position, Trade).outerjoin(Trade, Position.trade_id == Trade.id).order_by(Position.id.desc())

    if scope == "history":
        stmt = stmt.where(Position.is_open == False)
    elif scope == "all":
        pass  # return all positions
    else:  # Default: only open positions
        stmt = stmt.where(Position.is_open == True)

    res = await db.execute(stmt)
    rows = res.all()
    
    positions = []
    for pos, trade in rows:
        sub = market_data_service.subscriptions.get(pos.instrument_token)
        ltp = sub.get("latest_ltp") if sub else pos.average_price
        
        # Calculate unrealized PNL
        unrealized_pnl = 0.0
        if pos.is_open and ltp is not None:
            unrealized_pnl = (ltp - pos.average_price) * pos.quantity

        trade_status = "CLOSED"
        if trade:
            trade_status = trade.status.value if hasattr(trade.status, "value") else str(trade.status)
        elif pos.is_open:
            trade_status = "OPEN"

        positions.append({
            "id": pos.id,
            "trade_id": pos.trade_id,
            "instrument": pos.instrument_token,
            "quantity": pos.quantity,
            "average_entry": pos.average_price,
            "current_ltp": ltp,
            "unrealized_pnl": round(unrealized_pnl, 2),
            "is_open": pos.is_open,
            "state": trade_status,
            "created_at": to_utc_iso(pos.created_at)
        })
    return positions

@router.get("/orders")
async def get_orders(
    scope: Optional[str] = Query(None, description="Scope filter: 'current_session' (default), 'history', or 'all'"),
    db: AsyncSession = Depends(get_db)
):
    """
    List of orders with scope filtering.
    - Default or scope='current_session': Returns orders created in the current paper session.
    - scope='history': Returns historical orders created before the current paper session.
    - scope='all': Returns all historical and current orders.
    """
    # Determine current paper session boundary
    stmt_broker = select(BrokerAccount).where(BrokerAccount.is_paper_trading == True).limit(1)
    paper_broker_acc = (await db.execute(stmt_broker)).scalar_one_or_none()

    session_start = paper_broker_acc.paper_reset_at if paper_broker_acc else None
    if not session_start:
        stmt_last_reset = (
            select(AuditLog)
            .where(AuditLog.action == "PAPER_STATE_RESET")
            .order_by(AuditLog.id.desc())
            .limit(1)
        )
        last_reset = (await db.execute(stmt_last_reset)).scalar_one_or_none()
        if last_reset:
            session_start = last_reset.created_at

    now_utc = datetime.now(timezone.utc)
    today_start = now_utc.replace(hour=0, minute=0, second=0, microsecond=0)
    effective_session_start = session_start if session_start else today_start

    stmt = select(Order).order_by(Order.id.desc())

    if scope == "history":
        if session_start:
            stmt = stmt.where(Order.created_at < session_start)
    elif scope == "all":
        pass  # return all
    else:  # Default: current_session orders only
        stmt = stmt.where(Order.created_at >= effective_session_start)

    orders = (await db.execute(stmt)).scalars().all()
    
    return [
        {
            "id": o.id,
            "trade_id": o.trade_id,
            "broker_order_id": o.broker_order_id,
            "order_type": o.order_type,
            "quantity": o.quantity,
            "price": o.price,
            "status": o.status,
            "execution_type": "PAPER ORDER",
            "is_paper": True,
            "created_at": to_utc_iso(o.created_at)
        }
        for o in orders
    ]


# =========================================================================
# 6. MARKET DATA SUBSCRIPTIONS & STATUS
# =========================================================================
@router.get("/market-data/status")
async def get_market_data_status():
    return market_data_service.get_status()

@router.get("/market-data/health")
async def get_market_data_health():
    """
    Internal SFeed health and diagnostics endpoint (Task 11).
    Sanitized — never exposes credentials, session IDs, MPIN, or secrets.
    """
    sfeed_mgr = get_sfeed_manager()
    return sfeed_mgr.get_diagnostics()

@router.get("/market-data/subscriptions")
async def get_market_data_subscriptions():
    """Returns active subscriptions with real vs test data tag."""
    return market_data_service.get_subscriptions()


# =========================================================================
# 7. BROKER STATUS & RISK STATUS
# =========================================================================
@router.get("/broker/status")
async def get_broker_page_status():
    """
    Sanitized broker status with in-memory profile and instrument count caching.
    Never exposes consumer keys, access tokens, TOTP secrets, or session IDs.
    """
    is_connected = kotak_broker.auth_status == "CONNECTED"
    profile = None
    now_mono = time.time()
    if is_connected:
        if _profile_cache["data"] is not None and (now_mono - _profile_cache["timestamp"]) < PROFILE_CACHE_TTL_SECONDS:
            profile = _profile_cache["data"]
        else:
            try:
                profile = await kotak_broker.get_profile()
                _profile_cache["data"] = profile
                _profile_cache["timestamp"] = now_mono
            except Exception:
                profile = _profile_cache["data"]

    # Precompute / cache instrument counts instead of looping 50,000+ items every request
    resolver_cache = getattr(telegram_listener.resolver, "_cache", []) if hasattr(telegram_listener, "resolver") else []
    curr_scrip_len = len(resolver_cache)
    if curr_scrip_len > 0 and _scrip_count_cache["cache_id"] != curr_scrip_len:
        nifty_cnt = sum(1 for row in resolver_cache if row.get("pSymbolName") == "NIFTY")
        _scrip_count_cache["scrip_count"] = curr_scrip_len
        _scrip_count_cache["nifty_count"] = nifty_cnt
        _scrip_count_cache["cache_id"] = curr_scrip_len

    scrip_master_count = _scrip_count_cache["scrip_count"] or curr_scrip_len
    active_nifty_count = _scrip_count_cache["nifty_count"]

    sfeed_mgr = get_sfeed_manager()
    return {
        "broker_name": "Kotak Neo",
        "auth_status": kotak_broker.auth_status,
        "trading_session": "VALID" if is_connected else "DISCONNECTED",
        "scrip_master": "LOADED" if scrip_master_count > 0 else "PENDING",
        "instrument_count": scrip_master_count,
        "active_nifty_contracts": active_nifty_count,
        "sfeed_status": sfeed_mgr.state,
        "read_only": True,
        "live_orders": "DISABLED",
        "last_successful_request": kotak_broker.last_successful_request,
        "profile": {
            "client_code": profile.get("client_code") if profile else None,
            "account_status": "ACTIVE" if is_connected else "OFFLINE"
        } if profile else None
    }

class RiskConfigResponse(BaseModel):
    max_daily_loss: float
    max_risk_per_trade: float
    max_trades_per_day: int
    max_simultaneous_positions: int
    daily_loss_protection_enabled: bool
    max_trades_protection_enabled: bool
    max_positions_protection_enabled: bool
    is_algo_active: bool
    entry_timeout_minutes: int
    entry_tolerance: float
    partial_profit_enabled: bool
    partial_profit_trigger: float
    partial_profit_percentage: float
    trailing_stop_enabled: bool
    trailing_activation_mode: str
    trailing_activation_profit: float
    trailing_distance: float
    partial_profit_enabled: bool
    partial_profit_trigger: float
    partial_profit_percentage: float
    trailing_stop_enabled: bool
    trailing_activation_mode: str
    trailing_activation_profit: float
    updated_at: Optional[str] = None

class UpdateRiskConfigRequest(BaseModel):
    max_daily_loss: float
    max_risk_per_trade: float
    max_trades_per_day: int
    max_simultaneous_positions: int
    daily_loss_protection_enabled: Optional[bool] = True
    max_trades_protection_enabled: Optional[bool] = True
    max_positions_protection_enabled: Optional[bool] = True
    is_algo_active: Optional[bool] = True
    entry_timeout_minutes: Optional[int] = 15
    entry_tolerance: Optional[float] = 1.0
    
    partial_profit_enabled: Optional[bool] = False
    partial_profit_trigger: Optional[float] = 10.00
    partial_profit_percentage: Optional[float] = 50.0
    
    trailing_stop_enabled: Optional[bool] = False
    trailing_activation_mode: Optional[str] = "AFTER_PARTIAL_PROFIT"
    trailing_activation_profit: Optional[float] = 10.00
    trailing_distance: Optional[float] = 5.00

@router.get("/risk/config")
async def get_risk_config(db: AsyncSession = Depends(get_db)):
    """Fetch the active editable risk configuration."""
    stmt = select(TradingSettings).where(TradingSettings.user_id == 1)
    settings = (await db.execute(stmt)).scalar_one_or_none()

    if not settings:
        settings = TradingSettings(
            user_id=1,
            max_daily_loss=6000.0,
            max_risk_per_trade=2000.0,
            max_trades_per_day=5,
            max_simultaneous_positions=2,
            daily_loss_protection_enabled=True,
            max_trades_protection_enabled=True,
            max_positions_protection_enabled=True,
            is_algo_active=True,
            entry_timeout_minutes=15,
            entry_tolerance=1.0,
            partial_profit_enabled=False,
            partial_profit_trigger=10.0,
            partial_profit_percentage=50.0,
            trailing_stop_enabled=False,
            trailing_activation_mode="AFTER_PARTIAL_PROFIT",
            trailing_activation_profit=10.0,
            trailing_distance=5.0
        )
        db.add(settings)
        await db.commit()
        await db.refresh(settings)

    return {
        "max_daily_loss": float(settings.max_daily_loss),
        "max_risk_per_trade": float(getattr(settings, "max_risk_per_trade", 2000.0)),
        "max_trades_per_day": int(settings.max_trades_per_day),
        "max_simultaneous_positions": int(settings.max_simultaneous_positions),
        "daily_loss_protection_enabled": bool(getattr(settings, "daily_loss_protection_enabled", True)),
        "max_trades_protection_enabled": bool(getattr(settings, "max_trades_protection_enabled", True)),
        "max_positions_protection_enabled": bool(getattr(settings, "max_positions_protection_enabled", True)),
        "is_algo_active": bool(settings.is_algo_active),
        "entry_timeout_minutes": int(settings.entry_timeout_minutes if settings.entry_timeout_minutes is not None else 15),
        "entry_tolerance": float(settings.entry_tolerance if getattr(settings, "entry_tolerance", None) is not None else 1.0),
        "partial_profit_enabled": bool(getattr(settings, "partial_profit_enabled", False)),
        "partial_profit_trigger": float(getattr(settings, "partial_profit_trigger", 10.0)),
        "partial_profit_percentage": float(getattr(settings, "partial_profit_percentage", 50.0)),
        "trailing_stop_enabled": bool(getattr(settings, "trailing_stop_enabled", False)),
        "trailing_activation_mode": str(getattr(settings, "trailing_activation_mode", "AFTER_PARTIAL_PROFIT")),
        "trailing_activation_profit": float(getattr(settings, "trailing_activation_profit", 10.0)),
        "trailing_distance": float(getattr(settings, "trailing_distance", 5.0)),
        "updated_at": to_utc_iso(getattr(settings, "updated_at", None) or settings.created_at)
    }

@router.put("/risk/config")
async def update_risk_config(req: UpdateRiskConfigRequest, db: AsyncSession = Depends(get_db)):
    """Update active risk configuration with validation."""
    if req.max_daily_loss <= 0 or req.max_risk_per_trade <= 0:
        raise HTTPException(
            status_code=400,
            detail="Monetary values (max_daily_loss, max_risk_per_trade) must be greater than 0"
        )
    if req.max_trades_per_day <= 0:
        raise HTTPException(status_code=400, detail="max_trades_per_day must be at least 1")
    if req.max_simultaneous_positions <= 0:
        raise HTTPException(status_code=400, detail="max_simultaneous_positions must be at least 1")
    # Phase 10C: validate entry_timeout_minutes
    entry_timeout = req.entry_timeout_minutes if req.entry_timeout_minutes is not None else 15
    if not isinstance(entry_timeout, int) or entry_timeout < 1 or entry_timeout > 60:
        raise HTTPException(
            status_code=400,
            detail="entry_timeout_minutes must be an integer between 1 and 60"
        )
    entry_tolerance = req.entry_tolerance if req.entry_tolerance is not None else 1.0
    if entry_tolerance < 0 or entry_tolerance > 100:
        raise HTTPException(
            status_code=400,
            detail="entry_tolerance must be between 0 and 100"
        )

    stmt = select(TradingSettings).where(TradingSettings.user_id == 1)
    settings = (await db.execute(stmt)).scalar_one_or_none()

    if not settings:
        settings = TradingSettings(user_id=1)
        db.add(settings)

    settings.max_daily_loss = float(req.max_daily_loss)
    settings.max_risk_per_trade = float(req.max_risk_per_trade)
    settings.max_trades_per_day = int(req.max_trades_per_day)
    settings.max_simultaneous_positions = int(req.max_simultaneous_positions)
    settings.daily_loss_protection_enabled = bool(req.daily_loss_protection_enabled)
    settings.max_trades_protection_enabled = bool(req.max_trades_protection_enabled)
    settings.max_positions_protection_enabled = bool(req.max_positions_protection_enabled)
    settings.is_algo_active = bool(req.is_algo_active)
    settings.entry_timeout_minutes = int(entry_timeout)
    settings.entry_tolerance = float(entry_tolerance)
    settings.partial_profit_enabled = bool(req.partial_profit_enabled)
    settings.partial_profit_trigger = float(req.partial_profit_trigger)
    settings.partial_profit_percentage = float(req.partial_profit_percentage)
    settings.trailing_stop_enabled = bool(req.trailing_stop_enabled)
    settings.trailing_activation_mode = str(req.trailing_activation_mode)
    settings.trailing_activation_profit = float(req.trailing_activation_profit)
    settings.trailing_distance = float(req.trailing_distance)

    # Audit log
    audit = AuditLog(
        user_id=1,
        action="RISK_CONFIG_UPDATED",
        details={
            "max_daily_loss": req.max_daily_loss,
            "max_risk_per_trade": req.max_risk_per_trade,
            "max_trades_per_day": req.max_trades_per_day,
            "max_simultaneous_positions": req.max_simultaneous_positions,
            "entry_timeout_minutes": int(entry_timeout),
            "entry_tolerance": float(entry_tolerance),
            "daily_loss_protection_enabled": req.daily_loss_protection_enabled,
            "max_trades_protection_enabled": req.max_trades_protection_enabled,
            "max_positions_protection_enabled": req.max_positions_protection_enabled,
            "is_algo_active": req.is_algo_active,
            "partial_profit_enabled": req.partial_profit_enabled,
            "partial_profit_trigger": req.partial_profit_trigger,
            "partial_profit_percentage": req.partial_profit_percentage,
            "trailing_stop_enabled": req.trailing_stop_enabled,
            "trailing_activation_mode": req.trailing_activation_mode,
            "trailing_activation_profit": req.trailing_activation_profit,
            "trailing_distance": req.trailing_distance
        }
    )
    db.add(audit)
    await db.commit()
    await db.refresh(settings)

    return {
        "status": "SUCCESS",
        "message": "Risk configuration successfully updated",
        "config": {
            "max_daily_loss": float(settings.max_daily_loss),
            "max_risk_per_trade": float(settings.max_risk_per_trade),
            "max_trades_per_day": int(settings.max_trades_per_day),
            "max_simultaneous_positions": int(settings.max_simultaneous_positions),
            "daily_loss_protection_enabled": bool(settings.daily_loss_protection_enabled),
            "max_trades_protection_enabled": bool(settings.max_trades_protection_enabled),
            "max_positions_protection_enabled": bool(settings.max_positions_protection_enabled),
            "is_algo_active": bool(settings.is_algo_active),
            "entry_timeout_minutes": int(settings.entry_timeout_minutes if settings.entry_timeout_minutes is not None else 15),
            "entry_tolerance": float(settings.entry_tolerance if getattr(settings, "entry_tolerance", None) is not None else 1.0),
            "partial_profit_enabled": bool(settings.partial_profit_enabled),
            "partial_profit_trigger": float(settings.partial_profit_trigger),
            "partial_profit_percentage": float(settings.partial_profit_percentage),
            "trailing_stop_enabled": bool(settings.trailing_stop_enabled),
            "trailing_activation_mode": str(settings.trailing_activation_mode),
            "trailing_activation_profit": float(settings.trailing_activation_profit),
            "trailing_distance": float(settings.trailing_distance),
            "updated_at": to_utc_iso(getattr(settings, "updated_at", None) or settings.created_at)
        }
    }

@router.get("/risk/status")
async def get_risk_status(db: AsyncSession = Depends(get_db)):
    """Current risk limits and status."""
    stmt = select(TradingSettings).where(TradingSettings.user_id == 1)
    settings = (await db.execute(stmt)).scalar_one_or_none()

    today_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)

    # Check paper broker session boundary
    paper_stmt = select(BrokerAccount).where(BrokerAccount.user_id == 1, BrokerAccount.is_paper_trading == True)
    paper_account = (await db.execute(paper_stmt)).scalar_one_or_none()

    is_paper = paper_account is not None and paper_account.is_paper_trading
    session_start = paper_account.paper_reset_at if (is_paper and paper_account.paper_reset_at) else today_start
    risk_scope = "PAPER SESSION" if (is_paper and paper_account.paper_reset_at) else "CALENDAR DAY"

    # Count trades applicable to risk (excludes REJECTED trades)
    stmt_trades = select(func.count(Trade.id)).where(
        Trade.created_at >= session_start,
        Trade.status != TradeState.REJECTED
    )
    trades_used = (await db.execute(stmt_trades)).scalar() or 0

    open_positions = (await db.execute(select(func.count(Position.id)).where(Position.is_open == True))).scalar() or 0
    
    # Session realized P&L
    stmt_pnl = select(func.sum(Trade.realized_pnl)).where(Trade.created_at >= session_start)
    realized_pnl = (await db.execute(stmt_pnl)).scalar() or 0.0

    max_daily_loss = float(settings.max_daily_loss) if settings else 6000.0
    max_risk_per_trade = float(getattr(settings, "max_risk_per_trade", 2000.0)) if settings else 2000.0
    max_trades = int(settings.max_trades_per_day) if settings else 5
    max_positions = int(settings.max_simultaneous_positions) if settings else 2
    trades_remaining = max(0, max_trades - trades_used)

    daily_loss_enabled = getattr(settings, "daily_loss_protection_enabled", True) if settings else True
    max_trades_enabled = getattr(settings, "max_trades_protection_enabled", True) if settings else True
    max_positions_enabled = getattr(settings, "max_positions_protection_enabled", True) if settings else True

    # Check breach state & reasons
    new_trades_allowed = True
    active_rejection_reason = None

    if settings and not settings.is_algo_active:
        new_trades_allowed = False
        active_rejection_reason = "ALGO_NOT_ACTIVE"
    elif daily_loss_enabled and (realized_pnl <= -max_daily_loss):
        new_trades_allowed = False
        active_rejection_reason = "DAILY_LOSS_LIMIT_REACHED"
    elif max_trades_enabled and (trades_used >= max_trades):
        new_trades_allowed = False
        active_rejection_reason = "MAX_TRADES_PER_DAY_EXCEEDED"
    elif max_positions_enabled and (open_positions >= max_positions):
        new_trades_allowed = False
        active_rejection_reason = "MAX_SIMULTANEOUS_POSITIONS_EXCEEDED"

    remaining_daily_loss_allowance = max(0.0, max_daily_loss + float(realized_pnl))

    return {
        "limits": {
            "max_daily_loss": max_daily_loss,
            "max_risk_per_trade": max_risk_per_trade,
            "max_trades_per_day": max_trades,
            "max_simultaneous_positions": max_positions,
            "daily_loss_protection_enabled": daily_loss_enabled,
            "max_trades_protection_enabled": max_trades_enabled,
            "max_positions_protection_enabled": max_positions_enabled,
            "partial_profit_enabled": bool(getattr(settings, "partial_profit_enabled", False)) if settings else False,
            "partial_profit_trigger": float(getattr(settings, "partial_profit_trigger", 10.0)) if settings else 10.0,
            "partial_profit_percentage": float(getattr(settings, "partial_profit_percentage", 50.0)) if settings else 50.0,
            "trailing_stop_enabled": bool(getattr(settings, "trailing_stop_enabled", False)) if settings else False,
            "trailing_activation_mode": str(getattr(settings, "trailing_activation_mode", "AFTER_PARTIAL_PROFIT")) if settings else "AFTER_PARTIAL_PROFIT",
            "trailing_activation_profit": float(getattr(settings, "trailing_activation_profit", 10.0)) if settings else 10.0,
            "trailing_distance": float(getattr(settings, "trailing_distance", 5.0)) if settings else 5.0,
            "is_algo_active": settings.is_algo_active if settings else True
        },
        "current": {
            "trades_today": trades_used,
            "trades_used": trades_used,
            "trades_remaining": trades_remaining,
            "risk_scope": risk_scope,
            "open_positions": open_positions,
            "realized_pnl": float(realized_pnl),
            "remaining_daily_loss_allowance": remaining_daily_loss_allowance,
            "new_trades_allowed": new_trades_allowed,
            "active_rejection_reason": active_rejection_reason,
            "risk_status": "NORMAL" if new_trades_allowed else "BREACHED"
        }
    }


# =========================================================================
# 8. AUDIT LOGS
# =========================================================================
@router.get("/audit-logs")
async def get_audit_logs(limit: int = 100, db: AsyncSession = Depends(get_db)):
    """List of audit logs."""
    stmt = select(AuditLog).order_by(AuditLog.id.desc()).limit(limit)
    logs = (await db.execute(stmt)).scalars().all()

    result = []
    for l in logs:
        trade_id = None
        if isinstance(l.details, dict):
            trade_id = l.details.get("trade_id")
        elif isinstance(l.details, str):
            try:
                import json
                parsed = json.loads(l.details)
                if isinstance(parsed, dict):
                    trade_id = parsed.get("trade_id")
            except Exception:
                pass

        result.append({
            "id": l.id,
            "timestamp": to_utc_iso(l.created_at),
            "event": l.action,
            "trade_id": trade_id,
            "severity": "WARNING" if "REJECT" in l.action or "ERROR" in l.action else "INFO",
            "description": str(l.details)
        })
    return result


# =========================================================================
# 9. DEVELOPMENT / SIMULATION CONTROLS
# =========================================================================
class SimulateSignalRequest(BaseModel):
    underlying: str = "NIFTY"
    strike: int = 23500
    option_type: str = "CE"
    expiry: str = "2026-09-15"
    entry_trigger: float = 150.0
    stop_loss: float = 144.0
    target: float = 170.0

def format_expiry_for_telegram(expiry_input: str) -> str:
    try:
        dt = datetime.strptime(expiry_input.strip(), "%Y-%m-%d")
        months = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sept", "Oct", "Nov", "Dec"]
        month_name = months[dt.month - 1]
        return f"{dt.day:02d} {month_name} {str(dt.year)[-2:]} Expiry"
    except Exception:
        if "expiry" not in expiry_input.lower():
            return f"{expiry_input} Expiry"
        return expiry_input

@router.post("/paper/simulate-signal")
async def simulate_paper_signal(req: SimulateSignalRequest):
    """
    Paper Signal Simulator (Development Only).
    Does NOT bypass real parser.
    Constructs Telegram-style text and routes it through:
    Parser -> Database Persistence -> TradeManager -> Instrument Resolver -> SFeed/Paper market data flow.
    """
    formatted_expiry = format_expiry_for_telegram(req.expiry)
    # Construct standard telegram format
    telegram_text = (
        f"{req.underlying} {req.strike} {req.option_type} {formatted_expiry}\n"
        f"Buy above {req.entry_trigger}\n"
        f"SL below {req.stop_loss}\n"
        f"Tgt above {req.target}\n"
        f"CMP {req.entry_trigger}"
    )

    msg_id = f"SIM_{uuid.uuid4().hex[:8]}"
    channel_id = telegram_listener.selected_channel_id or "PAPER_SIMULATOR_CH"

    result = await telegram_listener.process_incoming_message(
        message_id=msg_id,
        channel_id=channel_id,
        text=telegram_text
    )

    return {
        "status": result.get("status"),
        "simulated_text": telegram_text,
        "message_id": msg_id,
        "parsed": result.get("parsed"),
        "trade_id": result.get("trade_id"),
        "instrument_token": result.get("instrument_token"),
        "errors": result.get("validation_errors")
    }

class InjectPriceRequest(BaseModel):
    instrument: str
    price: float

@router.post("/paper/inject-price")
async def inject_paper_price(req: InjectPriceRequest, db: AsyncSession = Depends(get_db)):
    """
    Market Data Test Control.
    Allows deterministic injection of mock prices into PaperBroker / market data flow.
    Clearly marked as TEST DATA.
    Evaluates entry/exit conditions for any active trades.
    """
    # Ingest into paper broker
    telegram_listener.paper_broker.inject_price(req.instrument, req.price)
    
    # Update market data service with "TEST DATA" tag
    market_data_service.update_tick(req.instrument, req.price, feed_type="TEST DATA")

    # Evaluate trades directly
    manager = TradeManager(db, telegram_listener.paper_broker)
    affected = await manager.evaluate_market_prices(req.instrument, req.price)

    return {
        "instrument": req.instrument,
        "price": req.price,
        "feed_type": "TEST DATA",
        "affected_trades": affected
    }


# =========================================================================
# 12. SAFE DEVELOPMENT PAPER TRADING RESET / CLEANUP
# =========================================================================
@router.post("/paper/reset")
async def reset_paper_state(db: AsyncSession = Depends(get_db)):
    """
    Safe Development-Only Paper Trading Reset Endpoint.
    
    Guarantees:
    - Works ONLY when application mode = PAPER.
    - Strictly refuses execution in LIVE mode.
    - Never calls KotakNeoBroker or any live order/exit API.
    - Never touches real broker positions.
    - Closes/resets ONLY paper positions (sets is_open = False) and active paper trades (sets status = CLOSED).
    - Preserves full audit history (no database records deleted).
    - Creates an audit event: PAPER_STATE_RESET.
    - Ensures RiskManager simultaneous positions count returns to 0.
    """
    # 1. Strict Mode Validation: Refuse execution if mode is LIVE
    current_mode = getattr(settings, "trading_mode", "PAPER").upper()
    if current_mode != "PAPER":
        raise HTTPException(
            status_code=400,
            detail="Paper reset rejected: Execution is strictly refused in LIVE mode."
        )

    # 2. Identify any live broker accounts to strictly guarantee they are never touched
    live_broker_stmt = select(BrokerAccount).where(BrokerAccount.is_paper_trading == False)
    live_accounts = (await db.execute(live_broker_stmt)).scalars().all()
    live_account_ids = {a.id for a in live_accounts}

    # 3. Inspect all currently open paper positions
    stmt_pos = (
        select(Position)
        .join(BrokerAccount, Position.broker_account_id == BrokerAccount.id)
        .where(Position.is_open == True, BrokerAccount.is_paper_trading == True)
    )
    res_pos = await db.execute(stmt_pos)
    open_paper_positions = res_pos.scalars().all()
    open_positions_count = len(open_paper_positions)

    # 4. Inspect active paper trades
    active_states = [
        TradeState.WAITING_FOR_ENTRY,
        TradeState.ENTRY_TRIGGERED,
        TradeState.ENTRY_ORDER_PENDING,
        TradeState.POSITION_OPEN,
        TradeState.PARTIAL_PROFIT,
        TradeState.TRAILING_STOP
    ]
    stmt_trades = (
        select(Trade)
        .join(BrokerAccount, Trade.broker_account_id == BrokerAccount.id)
        .where(Trade.status.in_(active_states), BrokerAccount.is_paper_trading == True)
    )
    res_trades = await db.execute(stmt_trades)
    active_paper_trades = res_trades.scalars().all()
    active_trades_count = len(active_paper_trades)

    # 5. Safely transition state WITHOUT physical database deletion
    now_utc = datetime.now(timezone.utc)
    new_session_id = f"SESSION_{now_utc.strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:4]}"

    # Query paper broker account to retrieve/update session boundary
    stmt_broker = select(BrokerAccount).where(BrokerAccount.is_paper_trading == True).limit(1)
    paper_account = (await db.execute(stmt_broker)).scalar_one_or_none()

    prev_session_id = paper_account.paper_session_id if paper_account else None
    if not prev_session_id:
        stmt_last_audit = (
            select(AuditLog)
            .where(AuditLog.action == "PAPER_STATE_RESET")
            .order_by(AuditLog.id.desc())
            .limit(1)
        )
        last_audit = (await db.execute(stmt_last_audit)).scalar_one_or_none()
        if last_audit and isinstance(last_audit.details, dict):
            prev_session_id = last_audit.details.get("new_session_identifier")
    if not prev_session_id:
        prev_session_id = "INITIAL_SESSION"

    # Calculate previous session P&L (all cumulative realized P&L prior to this reset)
    stmt_prev_pnl = select(func.sum(Trade.realized_pnl))
    prev_pnl = (await db.execute(stmt_prev_pnl)).scalar() or 0.0

    for pos in open_paper_positions:
        # Extra safety check: Ensure position belongs exclusively to paper broker
        if pos.broker_account_id in live_account_ids:
            continue
        pos.is_open = False

    for tr in active_paper_trades:
        # Extra safety check: Ensure trade belongs exclusively to paper broker
        if tr.broker_account_id in live_account_ids:
            continue
        tr.status = TradeState.CLOSED
        tr.updated_at = now_utc
        # Explicit safety: Preserve original entry info, do NOT set fake exit price, ensure P&L is 0.0
        tr.exit_price = None
        tr.realized_pnl = 0.0

    # Update paper broker account session boundary
    if paper_account:
        paper_account.paper_session_id = new_session_id
        paper_account.paper_reset_at = now_utc

    # 6. Reset in-memory PaperBroker state if present
    if hasattr(telegram_listener, "paper_broker") and telegram_listener.paper_broker:
        if hasattr(telegram_listener.paper_broker, "reset"):
            telegram_listener.paper_broker.reset()

    # 7. Record Audit Log for PAPER_STATE_RESET
    audit_entry = AuditLog(
        user_id=1,
        action="PAPER_STATE_RESET",
        details={
            "reset_timestamp": to_utc_iso(now_utc),
            "previous_open_positions": open_positions_count,
            "positions_reset": open_positions_count,
            "paper_trades_reset_closed": active_trades_count,
            "previous_session_identifier": prev_session_id,
            "new_session_identifier": new_session_id,
            "previous_session_pnl": float(prev_pnl),
            "new_session_pnl": 0.0,
            "live_broker_positions_touched": 0,
            "live_orders": "DISABLED",
            "reason": "DEVELOPMENT_PAPER_CLEANUP",
            "closure_reason": "PAPER_STATE_RESET"
        }
    )
    db.add(audit_entry)
    await db.commit()

    return {
        "status": "SUCCESS",
        "message": "Paper state successfully reset. New paper session started.",
        "session_id": new_session_id,
        "previous_session_id": prev_session_id,
        "open_positions_before_reset": open_positions_count,
        "positions_reset": open_positions_count,
        "paper_trades_reset_closed": active_trades_count,
        "current_session_pnl": 0.0,
        "previous_session_pnl": float(prev_pnl),
        "current_session_orders": 0,
        "live_broker_positions_touched": 0,
        "live_orders": "DISABLED"
    }

