"""
Trade Recovery Service for Application Restarts.

Queries persisted active trades (WAITING_FOR_ENTRY, POSITION_OPEN, PARTIAL_PROFIT, TRAILING_STOP)
and restores active market data subscriptions in MarketDataService & Kotak SFeed.
Ensures no active trade is orphaned when the backend service restarts.
"""
import logging
from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.database.database import AsyncSessionLocal
from app.database.models import Trade, TradeState, Signal
from app.services.market_data_service import market_data_service

logger = logging.getLogger(__name__)

ACTIVE_TRADE_STATES = [
    TradeState.WAITING_FOR_ENTRY,
    TradeState.ENTRY_TRIGGERED,
    TradeState.ENTRY_ORDER_PENDING,
    TradeState.POSITION_OPEN,
    TradeState.PARTIAL_PROFIT,
    TradeState.TRAILING_STOP,
]


async def restore_active_trades_subscriptions(db_session: Optional[AsyncSession] = None) -> int:
    """
    Restores market data subscriptions for all active, uncompleted trades upon application startup.
    Returns the count of active trades restored.
    """
    session_provided = db_session is not None
    session = db_session if session_provided else AsyncSessionLocal()

    restored_count = 0
    try:
        stmt = (
            select(Trade, Signal)
            .outerjoin(Signal, Trade.signal_id == Signal.id)
            .where(Trade.status.in_(ACTIVE_TRADE_STATES))
        )
        result = await session.execute(stmt)
        rows = result.all()

        for trade, signal in rows:
            token = str(trade.instrument_token).strip() if trade.instrument_token else None
            if not token:
                continue

            symbol = signal.underlying if signal else token
            strike = float(signal.strike) if (signal and signal.strike) else 0.0
            option_type = signal.option_type if signal else ""
            expiry = signal.expiry if signal else ""

            def _determine_exchange_segment(s: str) -> str:
                s_up = s.upper()
                if "SENSEX" in s_up or "BANKEX" in s_up:
                    return "bse_fo"
                elif "MCX" in s_up:
                    return "mcx_fo"
                return "nse_fo"

            exchange_seg = _determine_exchange_segment(symbol)

            market_data_service.register_trade_interest(
                token=token,
                trade_id=trade.id,
                symbol=signal.underlying if signal and signal.underlying else symbol,
                exchange_seg=exchange_seg,
                strike=strike,
                option_type=option_type,
                expiry=expiry,
            )
            restored_count += 1
            logger.info(
                f"[TRADE_RECOVERY] Restored subscription for trade #{trade.id} "
                f"({trade.status.value}) on token {token}"
            )

        logger.info(f"[TRADE_RECOVERY] Successfully restored {restored_count} active trade subscriptions.")
        return restored_count

    except Exception as e:
        logger.error(f"[TRADE_RECOVERY] Error restoring active trades: {e}", exc_info=True)
        return 0
    finally:
        if not session_provided:
            await session.close()
