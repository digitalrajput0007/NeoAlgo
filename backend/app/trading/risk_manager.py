from decimal import Decimal
from typing import Optional, Tuple
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from app.database.models import TradingSettings, Trade, TradeState, RiskEvent, BrokerAccount
from datetime import datetime, timezone
import logging

logger = logging.getLogger(__name__)


class RiskManager:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_active_settings(self, user_id: Optional[int] = 1) -> TradingSettings:
        """Fetch active trading/risk settings for user or default global configuration."""
        stmt = select(TradingSettings).where(
            (TradingSettings.user_id == user_id) | (TradingSettings.user_id.is_(None))
        ).order_by(TradingSettings.id.desc()).limit(1)
        result = await self.db.execute(stmt)
        settings = result.scalar_one_or_none()

        if not settings:
            # Fallback in-memory default settings if DB record not found
            settings = TradingSettings(
                user_id=user_id,
                max_daily_loss=6000.0,
                max_risk_per_trade=2000.0,
                max_trades_per_day=5,
                max_simultaneous_positions=2,
                daily_loss_protection_enabled=True,
                max_trades_protection_enabled=True,
                max_positions_protection_enabled=True,
                is_algo_active=True
            )
        return settings

    async def check_new_trade_allowed(
        self,
        user_id: int,
        broker_account_id: Optional[int] = None,
        entry_trigger: Optional[float] = None,
        stop_loss: Optional[float] = None,
        quantity: Optional[int] = None
    ) -> Tuple[bool, str]:
        """
        Check if a new trade is allowed based on active TradingSettings.
        Enforces:
          1. Algo active status
          2. Daily loss limit (scoped to session boundary, with Decimal precision)
          3. Maximum trades per day/session
          4. Maximum simultaneous positions
          5. Estimated risk per trade: (entry - sl) * quantity <= max_risk_per_trade
        Returns (is_allowed, reason).
        """
        settings = await self.get_active_settings(user_id)

        if not settings.is_algo_active:
            return False, "ALGO_NOT_ACTIVE"

        # Determine session boundary based on broker account
        now_utc = datetime.now(timezone.utc)
        today_start = datetime(now_utc.year, now_utc.month, now_utc.day, tzinfo=timezone.utc)
        session_start = today_start

        # Query broker account to check for paper session reset boundary
        paper_account = None
        if broker_account_id:
            broker_stmt = select(BrokerAccount).where(BrokerAccount.id == broker_account_id)
            paper_account = (await self.db.execute(broker_stmt)).scalar_one_or_none()
        if not paper_account:
            broker_stmt = select(BrokerAccount).where(
                BrokerAccount.user_id == user_id,
                BrokerAccount.is_paper_trading == True
            )
            paper_account = (await self.db.execute(broker_stmt)).scalar_one_or_none()

        if paper_account and paper_account.is_paper_trading and paper_account.paper_reset_at:
            session_start = paper_account.paper_reset_at

        # 1. Check max daily loss (scoped to session boundary, Decimal arithmetic)
        is_daily_loss_enabled = getattr(settings, "daily_loss_protection_enabled", True)
        if is_daily_loss_enabled:
            stmt_pnl = select(Trade).where(
                Trade.user_id == user_id,
                Trade.created_at >= session_start
            )
            result_pnl = await self.db.execute(stmt_pnl)
            daily_trades = result_pnl.scalars().all()
            daily_pnl = sum([Decimal(str(t.realized_pnl or 0.0)) for t in daily_trades])
            max_daily_loss = Decimal(str(settings.max_daily_loss))

            if daily_pnl <= -max_daily_loss:
                logger.warning(f"[RISK] Daily loss limit breached: {daily_pnl} <= -{max_daily_loss}")
                return False, "DAILY_LOSS_LIMIT_REACHED"

        # 2. Check max trades per day / session
        # Excludes REJECTED trades which took no market risk and executed zero orders.
        is_max_trades_enabled = getattr(settings, "max_trades_protection_enabled", True)
        if is_max_trades_enabled:
            stmt_trades = select(Trade).where(
                Trade.user_id == user_id,
                Trade.created_at >= session_start,
                Trade.status != TradeState.REJECTED
            )
            result_trades = await self.db.execute(stmt_trades)
            applicable_trades = result_trades.scalars().all()
            trades_count = len(applicable_trades)

            if trades_count >= settings.max_trades_per_day:
                logger.warning(f"[RISK] Max trades per day exceeded: {trades_count} >= {settings.max_trades_per_day}")
                return False, "MAX_TRADES_PER_DAY_EXCEEDED"

        # 3. Check max simultaneous positions
        is_max_pos_enabled = getattr(settings, "max_positions_protection_enabled", True)
        if is_max_pos_enabled:
            stmt_pos = select(Trade).where(
                Trade.user_id == user_id,
                Trade.status.in_([
                    TradeState.WAITING_FOR_ENTRY,
                    TradeState.ENTRY_TRIGGERED,
                    TradeState.ENTRY_ORDER_PENDING,
                    TradeState.POSITION_OPEN,
                    TradeState.PARTIAL_PROFIT,
                    TradeState.TRAILING_STOP
                ])
            )
            result_pos = await self.db.execute(stmt_pos)
            active_trades = len(result_pos.scalars().all())

            if active_trades >= settings.max_simultaneous_positions:
                logger.warning(f"[RISK] Max simultaneous positions exceeded: {active_trades} >= {settings.max_simultaneous_positions}")
                return False, "MAX_SIMULTANEOUS_POSITIONS_EXCEEDED"

        # 4. Check max risk per trade
        if entry_trigger is not None and stop_loss is not None:
            entry_dec = Decimal(str(entry_trigger))
            sl_dec = Decimal(str(stop_loss))
            qty_dec = Decimal(str(quantity if quantity and quantity > 0 else 75))
            risk_per_unit = max(Decimal("0.0"), entry_dec - sl_dec)
            estimated_risk = risk_per_unit * qty_dec
            max_risk_allowed = Decimal(str(settings.max_risk_per_trade))

            if estimated_risk > max_risk_allowed:
                logger.warning(
                    f"[RISK] Trade risk exceeded: estimated {estimated_risk} > max allowed {max_risk_allowed} "
                    f"(trigger={entry_dec}, sl={sl_dec}, qty={qty_dec})"
                )
                return False, "MAX_RISK_PER_TRADE_EXCEEDED"

        return True, "OK"

    async def record_risk_event(self, user_id: int, event_type: str, description: str, trade_id: int = None):
        event = RiskEvent(
            user_id=user_id,
            trade_id=trade_id,
            event_type=event_type,
            description=description
        )
        self.db.add(event)
        logger.warning(f"[RISK EVENT] {user_id}: {event_type} - {description}")
