"""
Entry Expiry Sweeper — Phase 10C
=================================
A restart-safe, idempotent, periodic background task that cancels
WAITING_FOR_ENTRY trades whose entry_expires_at deadline has passed.

Design principles:
- One sweeper for ALL trades (not one asyncio.Task per trade).
- Reads entry_expires_at from the database every 30 s — survives server restarts.
- Uses a single transaction per sweep batch to guarantee atomicity.
- Idempotent: checks trade.status inside the transaction before cancelling.
- Calls market_data_service.release_trade_interest() to release SFeed reference.
- Writes AuditLog with full auditable details on each cancellation.
- Never calls KotakNeoBroker.place_order().  Trading mode remains PAPER.
"""

import asyncio
import logging
from datetime import datetime, timezone

from sqlalchemy.future import select

from app.database.database import AsyncSessionLocal
from app.database.models import Trade, TradeState, Signal, AuditLog

logger = logging.getLogger(__name__)

# How often the sweeper polls the database (seconds).
# 30 s gives <= 30 s overshoot on a 1-minute minimum timeout.
SWEEP_INTERVAL_SECONDS = 30


class EntryExpirySweeper:
    """Periodic sweeper that cancels expired WAITING_FOR_ENTRY trades."""

    def __init__(self):
        self._running = False

    async def sweep_once(self) -> int:
        """
        Run a single sweep pass.
        Returns the number of trades cancelled in this pass.
        """
        now_utc = datetime.now(timezone.utc)
        cancelled_count = 0

        try:
            async with AsyncSessionLocal() as session:
                # Find all WAITING_FOR_ENTRY trades with a past deadline
                stmt = (
                    select(Trade, Signal)
                    .outerjoin(Signal, Trade.signal_id == Signal.id)
                    .where(
                        Trade.status == TradeState.WAITING_FOR_ENTRY,
                        Trade.entry_expires_at.is_not(None),
                        Trade.entry_expires_at <= now_utc,
                    )
                )
                rows = (await session.execute(stmt)).all()

                for trade, signal in rows:
                    # Re-read status inside transaction to guard against concurrent entry
                    if trade.status != TradeState.WAITING_FOR_ENTRY:
                        logger.info(
                            f"[EXPIRY_SWEEPER] Trade #{trade.id} already left WAITING_FOR_ENTRY "
                            f"(status={trade.status.value}) — skipping."
                        )
                        continue

                    old_status = trade.status.value
                    trade.status = TradeState.CANCELLED
                    trade.cancel_reason = "SIGNAL_ENTRY_TIMEOUT"

                    # Release SFeed market data interest
                    token = trade.instrument_token or ""
                    if token:
                        try:
                            from app.services.market_data_service import market_data_service
                            market_data_service.release_trade_interest(token, trade.id)
                            logger.info(
                                f"[EXPIRY_SWEEPER] Released SFeed interest for trade #{trade.id} token={token}"
                            )
                        except Exception as e:
                            logger.warning(
                                f"[EXPIRY_SWEEPER] Failed to release SFeed interest for trade #{trade.id}: {e}"
                            )

                    # Audit log with full details
                    audit = AuditLog(
                        user_id=trade.user_id,
                        action="ENTRY_TIMEOUT_CANCELLED",
                        details={
                            "trade_id": trade.id,
                            "signal_id": trade.signal_id,
                            "instrument": token,
                            "entry_trigger": float(signal.entry_trigger) if signal and signal.entry_trigger else None,
                            "entry_timeout_minutes": trade.entry_timeout_minutes,
                            "entry_expires_at": trade.entry_expires_at.isoformat() if trade.entry_expires_at else None,
                            "now_utc": now_utc.isoformat(),
                            "cancel_reason": "SIGNAL_ENTRY_TIMEOUT",
                            "previous_status": old_status,
                        }
                    )
                    session.add(audit)

                    logger.warning(
                        f"[EXPIRY_SWEEPER] Trade #{trade.id} EXPIRED → CANCELLED "
                        f"(token={token}, timeout={trade.entry_timeout_minutes}m, "
                        f"expires_at={trade.entry_expires_at})"
                    )
                    cancelled_count += 1

                if cancelled_count > 0:
                    await session.commit()
                    logger.info(f"[EXPIRY_SWEEPER] Cancelled {cancelled_count} expired trade(s) in this pass.")

        except Exception as e:
            logger.error(f"[EXPIRY_SWEEPER] Sweep error: {e}", exc_info=True)

        return cancelled_count

    async def run(self):
        """Main loop: run sweep_once() every SWEEP_INTERVAL_SECONDS."""
        self._running = True
        logger.info(f"[EXPIRY_SWEEPER] Started (interval={SWEEP_INTERVAL_SECONDS}s).")

        # Immediate startup sweep to recover trades that expired during downtime
        await self.sweep_once()

        while self._running:
            try:
                await asyncio.sleep(SWEEP_INTERVAL_SECONDS)
                if self._running:
                    await self.sweep_once()
            except asyncio.CancelledError:
                logger.info("[EXPIRY_SWEEPER] Cancelled — stopping.")
                break
            except Exception as e:
                logger.error(f"[EXPIRY_SWEEPER] Unexpected error in run loop: {e}", exc_info=True)

    async def stop(self):
        self._running = False


# Singleton instance
entry_expiry_sweeper = EntryExpirySweeper()
