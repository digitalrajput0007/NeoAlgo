"""
NEOALGO REAL-MARKET PAPER SOAK TEST HARNESS

Monitors real SFeed ticks, real Telegram listener events, and PaperBroker execution
during live or paper market sessions without placing any live broker orders.

SAFETY:
- LIVE ORDERS STRICTLY DISABLED.
- Never calls KotakNeoBroker.place_order().
- All executions route exclusively to PaperBroker.
- Zero credentials or secrets logged.
"""
import asyncio
import logging
import os
import sys
import time
from datetime import datetime, timezone
from typing import Dict, Any

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.brokers.kotak_neo import get_kotak_broker
from app.market_data.kotak_neo_feed import get_sfeed_manager
from app.services.market_data_service import market_data_service
from app.services.telegram_listener import telegram_listener
from app.database.database import AsyncSessionLocal
from app.database.models import Trade, TradeState, Order, Position

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("SOAK_TEST")


class SoakTestMonitor:
    def __init__(self):
        self.start_time = time.time()
        self.broker = get_kotak_broker()
        self.sfeed = get_sfeed_manager(self.broker)
        self.metrics: Dict[str, Any] = {
            "start_time": datetime.now(timezone.utc).isoformat(),
            "total_real_ticks": 0,
            "total_signals": 0,
            "accepted_signals": 0,
            "rejected_signals": 0,
            "active_trades": 0,
            "paper_orders": 0,
            "completed_trades": 0,
            "duplicate_events": 0,
            "reconnects": 0,
            "stale_events": 0,
            "exceptions": 0,
            "current_session_pnl": 0.0,
            "live_order_invocations": 0,
        }

    async def collect_metrics(self):
        """Periodically polls the database and services to update soak test metrics."""
        self.metrics["total_real_ticks"] = market_data_service.total_ticks_received
        self.metrics["reconnects"] = getattr(self.sfeed, "reconnect_count", 0)
        self.metrics["live_order_invocations"] = getattr(self.broker, "_place_order_call_count", 0)

        # Ensure live orders remain strictly 0
        if self.metrics["live_order_invocations"] > 0:
            logger.critical("FATAL: Live order invocation detected during soak test! Halting immediately.")
            sys.exit(1)

        try:
            async with AsyncSessionLocal() as session:
                from sqlalchemy.future import select
                trades = (await session.execute(select(Trade))).scalars().all()
                self.metrics["total_signals"] = len(trades)
                self.metrics["accepted_signals"] = len([t for t in trades if t.status != TradeState.REJECTED])
                self.metrics["rejected_signals"] = len([t for t in trades if t.status == TradeState.REJECTED])
                self.metrics["active_trades"] = len([
                    t for t in trades if t.status in [
                        TradeState.WAITING_FOR_ENTRY, TradeState.POSITION_OPEN,
                        TradeState.ENTRY_TRIGGERED, TradeState.PARTIAL_PROFIT, TradeState.TRAILING_STOP
                    ]
                ])
                self.metrics["completed_trades"] = len([t for t in trades if t.status == TradeState.CLOSED])
                self.metrics["current_session_pnl"] = sum([t.realized_pnl or 0.0 for t in trades])

                orders = (await session.execute(select(Order))).scalars().all()
                self.metrics["paper_orders"] = len(orders)
        except Exception as e:
            self.metrics["exceptions"] += 1
            logger.error(f"Error querying soak test metrics: {e}")

    def print_summary(self):
        uptime = time.time() - self.start_time
        print("\n" + "=" * 70)
        print(f"NEOALGO SOAK TEST SUMMARY — Uptime: {uptime:.1f}s")
        print("=" * 70)
        for k, v in self.metrics.items():
            print(f"  {k:<28}: {v}")
        print("=" * 70)

    async def run(self, duration_seconds: int = 60):
        """Runs the soak monitor for duration_seconds or indefinitely if <= 0."""
        logger.info(f"Starting Soak Test Monitor (target duration: {duration_seconds}s)...")
        end_time = time.time() + duration_seconds if duration_seconds > 0 else float("inf")

        try:
            while time.time() < end_time:
                await self.collect_metrics()
                self.print_summary()
                await asyncio.sleep(10)
        except asyncio.CancelledError:
            logger.info("Soak test monitor cancelled.")
        finally:
            await self.collect_metrics()
            self.print_summary()


async def main():
    import argparse
    parser = argparse.ArgumentParser(description="NeoAlgo Real-Market Paper Soak Test Harness")
    parser.add_argument("--duration", type=int, default=30, help="Duration in seconds (default: 30)")
    args = parser.parse_args()

    monitor = SoakTestMonitor()
    await monitor.run(duration_seconds=args.duration)


if __name__ == "__main__":
    asyncio.run(main())
