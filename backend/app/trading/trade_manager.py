import logging
import math
from typing import Optional, List
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from datetime import datetime, timezone, timedelta
from decimal import Decimal

from app.database.models import Trade, TradeState, Signal, AuditLog, Order, Position, TradingSettings, TelegramMessage, TradeEvent
from app.telegram.models import TradeSignal, TelegramMessageType, ParseResult
from app.brokers.base import BrokerInterface
from app.trading.risk_manager import RiskManager

logger = logging.getLogger(__name__)

class TradeManager:
    def __init__(self, db: AsyncSession, broker: BrokerInterface):
        self.db = db
        self.broker = broker
        self.risk_manager = RiskManager(db)

    async def _log_trade_event(self, trade_id: int, event_type: str, price: Optional[float] = None, quantity: Optional[int] = None, metadata: Optional[dict] = None):
        event = TradeEvent(
            trade_id=trade_id,
            event_type=event_type,
            price=price,
            quantity=quantity,
            metadata_json=metadata
        )
        self.db.add(event)
        # We don't flush immediately here to save round trips, it will commit with the main transaction.

    async def _log_audit(self, user_id: int, trade_id: Optional[int], action: str, details: dict):
        log = AuditLog(
            user_id=user_id,
            action=action,
            details={"trade_id": trade_id, **details}
        )
        self.db.add(log)
        logger.info(f"[AUDIT] {action}: {details}")

    async def get_instrument_token(self, underlying: str, strike: int, option_type: str, expiry: str) -> str:
        res = await self.broker.resolve_option_contract(underlying, strike, option_type, expiry)
        return str(res.get("pSymbol") or res.get("instrument_token"))

    async def is_duplicate_message(self, message_id: str, channel_id: str) -> bool:
        stmt = select(TelegramMessage).where(
            TelegramMessage.telegram_message_id == str(message_id),
            TelegramMessage.channel_id == str(channel_id)
        )
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none() is not None

    async def record_telegram_message(self, message_id: str, channel_id: str, text: str, parsed: ParseResult):
        msg = TelegramMessage(
            telegram_message_id=str(message_id),
            channel_id=str(channel_id),
            message_text=text,
            message_type=parsed.message_type,
            parsed_successfully=parsed.parsed_successfully,
            error_message=", ".join(parsed.validation_errors) if parsed.validation_errors else None
        )
        self.db.add(msg)
        await self.db.flush()

    async def process_new_signal(
        self,
        user_id: int,
        broker_account_id: int,
        signal_data: TradeSignal,
        message_id: str,
        resolved_token: Optional[str] = None
    ) -> Trade:
        """Process a validated NEW_SIGNAL into a Trade."""
        
        # Determine instrument token first
        if resolved_token:
            instrument_token = str(resolved_token)
        else:
            instrument_token = await self.get_instrument_token(
                signal_data.underlying, 
                signal_data.strike, 
                signal_data.option_type, 
                signal_data.expiry.isoformat() if signal_data.expiry else None
            )

        # Resolve contract lot size for risk sizing
        lot_size = 75
        try:
            from app.services.market_data_service import market_data_service
            sub_info = market_data_service.subscriptions.get(instrument_token, {})
            lot_size = int(sub_info.get("lot_size", 75)) or 75
        except Exception:
            pass

        active_settings = await self.risk_manager.get_active_settings(user_id)
        is_allowed = True
        reason = None
        
        # 0. Check if globally paused
        if active_settings and getattr(active_settings, "new_trades_paused", False):
            is_allowed = False
            reason = "NEW_TRADES_PAUSED"

        # 1. Check Risk constraints with entry, stop loss, and lot size
        if is_allowed:
            is_allowed, reason = await self.risk_manager.check_new_trade_allowed(
                user_id,
                broker_account_id=broker_account_id,
                entry_trigger=float(signal_data.entry_trigger) if signal_data.entry_trigger is not None else None,
                stop_loss=float(signal_data.stop_loss) if signal_data.stop_loss is not None else None,
                quantity=lot_size
            )

        # Build risk configuration snapshot if accepted
        risk_snapshot = None
        if is_allowed:
            risk_snapshot = {
                "max_daily_loss": float(active_settings.max_daily_loss),
                "max_risk_per_trade": float(active_settings.max_risk_per_trade),
                "max_trades_per_day": int(active_settings.max_trades_per_day),
                "max_simultaneous_positions": int(active_settings.max_simultaneous_positions),
                "daily_loss_protection_enabled": bool(getattr(active_settings, "daily_loss_protection_enabled", True)),
                "max_trades_protection_enabled": bool(getattr(active_settings, "max_trades_protection_enabled", True)),
                "max_positions_protection_enabled": bool(getattr(active_settings, "max_positions_protection_enabled", True)),
                "entry_timeout_minutes": int(getattr(active_settings, "entry_timeout_minutes", 15)),
                "evaluated_at": datetime.now(timezone.utc).isoformat()
            }

        # Create Signal DB record
        db_signal = Signal(
            message_id=message_id,
            underlying=signal_data.underlying,
            strike=float(signal_data.strike),
            option_type=signal_data.option_type,
            expiry=signal_data.expiry.isoformat(),
            entry_trigger=float(signal_data.entry_trigger),
            stop_loss=float(signal_data.stop_loss),
            target=float(signal_data.target),
            telegram_cmp=float(signal_data.telegram_cmp) if signal_data.telegram_cmp else None
        )
        self.db.add(db_signal)
        await self.db.flush()

        # Phase 10C: compute frozen entry expiry timestamp
        # Timer starts from the signal's canonical created_at timestamp (set by SQLAlchemy
        # Determine initial state
        initial_state = TradeState.WAITING_FOR_ENTRY if is_allowed else TradeState.REJECTED

        # Retrieve entry timeout and tolerance from settings (fallback to default)
        entry_timeout_mins = int(getattr(active_settings, "entry_timeout_minutes", 15)) if active_settings and getattr(active_settings, "entry_timeout_minutes", None) is not None else 15
        entry_tolerance = float(getattr(active_settings, "entry_tolerance", 1.0)) if active_settings and getattr(active_settings, "entry_tolerance", None) is not None else 1.0

        # Calculate absolute bounds using Decimal for exactness
        signal_trigger_dec = Decimal(str(db_signal.entry_trigger))
        tolerance_dec = Decimal(str(entry_tolerance))
        entry_lower_bound = float(signal_trigger_dec - tolerance_dec)
        entry_upper_bound = float(signal_trigger_dec + tolerance_dec)

        entry_expires_at = None
        if initial_state == TradeState.WAITING_FOR_ENTRY:
            entry_expires_at = datetime.now(timezone.utc) + timedelta(minutes=entry_timeout_mins)

        # Create Trade DB record
        trade = Trade(
            user_id=user_id,
            signal_id=db_signal.id,
            broker_account_id=broker_account_id,
            status=initial_state,
            instrument_token=instrument_token,
            quantity=0, # Will be populated on entry
            risk_snapshot=risk_snapshot,
            entry_timeout_minutes=entry_timeout_mins,
            entry_expires_at=entry_expires_at,
            entry_tolerance=entry_tolerance,
            entry_lower_bound=entry_lower_bound,
            entry_upper_bound=entry_upper_bound,
            entry_direction=getattr(signal_data, "entry_direction", None),
            
            partial_profit_enabled=bool(getattr(active_settings, "partial_profit_enabled", False)) if active_settings else False,
            partial_profit_trigger=float(getattr(active_settings, "partial_profit_trigger", 10.0)) if active_settings else 10.0,
            partial_profit_percentage=float(getattr(active_settings, "partial_profit_percentage", 50.0)) if active_settings else 50.0,
            trailing_stop_enabled=bool(getattr(active_settings, "trailing_stop_enabled", False)) if active_settings else False,
            trailing_activation_mode=str(getattr(active_settings, "trailing_activation_mode", "AFTER_PARTIAL_PROFIT")) if active_settings else "AFTER_PARTIAL_PROFIT",
            trailing_activation_profit=float(getattr(active_settings, "trailing_activation_profit", 10.0)) if active_settings else 10.0,
            trailing_distance=float(getattr(active_settings, "trailing_distance", 5.0)) if active_settings else 5.0,
        )
        self.db.add(trade)
        await self.db.flush()
        
        await self._log_trade_event(trade.id, "SIGNAL_RECEIVED", price=getattr(db_signal, "telegram_cmp", None))

        if not is_allowed:
            await self.risk_manager.record_risk_event(user_id, "RISK_REJECTED", reason, trade.id)
            await self._log_audit(user_id, trade.id, "RISK_REJECTED", {"reason": reason, "instrument": instrument_token})
            await self._log_trade_event(trade.id, "TRADE_REJECTED", metadata={"reason": reason})
        else:
            await self._log_audit(user_id, trade.id, "TRADE_CREATED", {
                "instrument": instrument_token,
                "state": initial_state.value,
                "entry_timeout_minutes": entry_timeout_mins,
                "entry_expires_at": entry_expires_at.isoformat() if entry_expires_at else None,
            })
            await self._log_trade_event(trade.id, "TRADE_ACCEPTED")
            if initial_state == TradeState.WAITING_FOR_ENTRY:
                await self._log_trade_event(trade.id, "WAITING_FOR_ENTRY", metadata={"timeout_mins": entry_timeout_mins})

        await self.db.commit()
        return trade

    async def _place_paper_order(self, trade: Trade, side: str, quantity: int, price: float):
        order_params = {
            "instrument_token": trade.instrument_token,
            "transaction_type": side,
            "quantity": quantity,
            "price": price,
            "order_type": "MARKET"
        }
        broker_order = await self.broker.place_order(order_params)
        
        db_order = Order(
            trade_id=trade.id,
            broker_order_id=broker_order["order_id"],
            order_type=side,
            quantity=quantity,
            price=broker_order["price"],
            status=broker_order["status"]
        )
        self.db.add(db_order)
        await self.db.flush()
        
        await self._log_trade_event(trade.id, "ENTRY_ORDER_CREATED", price=price, quantity=quantity, metadata={"order_id": db_order.broker_order_id, "side": side})
        await self._log_audit(trade.user_id, trade.id, "ORDER_CREATED", {"side": side, "quantity": quantity, "price": price})
        return db_order

    async def _update_position(self, trade: Trade, side: str, quantity: int, price: float):
        # Find existing position
        stmt = select(Position).where(Position.trade_id == trade.id)
        result = await self.db.execute(stmt)
        position = result.scalar_one_or_none()
        
        if side == "BUY":
            if not position:
                position = Position(
                    user_id=trade.user_id,
                    trade_id=trade.id,
                    broker_account_id=trade.broker_account_id,
                    instrument_token=trade.instrument_token,
                    quantity=quantity,
                    average_price=price,
                    is_open=True
                )
                self.db.add(position)
            else:
                position.quantity += quantity
                position.is_open = position.quantity > 0
                
            trade.quantity += quantity
            trade.entry_price = price
            
            await self._log_trade_event(trade.id, "POSITION_OPENED", price=price, quantity=quantity)
            await self._log_audit(trade.user_id, trade.id, "POSITION_OPENED", {"quantity": quantity, "price": price})
            
        elif side == "SELL":
            if position:
                # Calculate Realized PNL for this chunk
                realized_pnl_chunk = (price - position.average_price) * quantity
                position.quantity -= quantity
                if position.quantity <= 0:
                    position.is_open = False
                    position.quantity = 0
                    
                trade.quantity -= quantity
                trade.realized_pnl = (trade.realized_pnl or 0.0) + realized_pnl_chunk
                trade.exit_price = price # track last exit price
                
                await self._log_audit(trade.user_id, trade.id, "POSITION_CLOSED_PARTIAL" if position.quantity > 0 else "POSITION_CLOSED", {"quantity": quantity, "price": price, "pnl": realized_pnl_chunk})
                
        await self.db.flush()

    def _release_interest(self, trade: Trade):
        try:
            from app.services.market_data_service import market_data_service
            market_data_service.release_trade_interest(trade.instrument_token, trade.id)
        except Exception:
            pass


    async def evaluate_market_prices(self, instrument_token: str, ltp: float) -> List[dict]:
        """Evaluates entry/exit conditions for all active trades matching the instrument token."""
        # Failure-Closed: Reject missing, non-positive, NaN, or non-numeric LTP
        if ltp is None or not isinstance(ltp, (int, float)) or ltp <= 0 or math.isnan(ltp):
            logger.warning(f"[TRADE_MANAGER] Rejected invalid market tick for token {instrument_token}: ltp={ltp}")
            return []

        stmt = (
            select(Trade, Signal)
            .join(Signal, Trade.signal_id == Signal.id)
            .where(
                Trade.instrument_token == instrument_token,
                Trade.status.in_([
                    TradeState.WAITING_FOR_ENTRY,
                    TradeState.POSITION_OPEN,
                    TradeState.PARTIAL_PROFIT,
                    TradeState.TRAILING_STOP
                ])
            )
        )
        result = await self.db.execute(stmt)
        active_rows = []
        try:
            raw_rows = result.all()
            if isinstance(raw_rows, (list, tuple)) and len(raw_rows) > 0 and hasattr(raw_rows[0], "__len__") and len(raw_rows[0]) == 2:
                active_rows = raw_rows
            elif isinstance(raw_rows, (list, tuple)) and len(raw_rows) == 0:
                active_rows = []
            else:
                raise TypeError("Non-tuple rows returned from execute")
        except Exception:
            # Fallback for mock environments (e.g. unit tests mocking result.scalars())
            try:
                trades_list = result.scalars().all()
                for t in trades_list:
                    sig_stmt = select(Signal).where(Signal.id == t.signal_id)
                    sig_res = await self.db.execute(sig_stmt)
                    sig = sig_res.scalar_one()
                    active_rows.append((t, sig))
            except Exception:
                active_rows = []
        
        affected_trades = []
        
        for trade, signal in active_rows:
            prev_state = trade.status
            state_changed = False
            
            if trade.status == TradeState.WAITING_FOR_ENTRY:
                # Requirement 13: Do not use stale market data to trigger a new paper entry.
                from app.services.market_data_service import market_data_service
                if market_data_service.is_stale(instrument_token):
                    logger.warning(f"[TRADE_MANAGER] Entry blocked: Market data for {instrument_token} is stale.")
                    continue

                # Phase 10C: Block entry if the entry deadline has already passed.
                # The sweeper will cancel the trade on its next pass; we must not
                # allow a tick that arrives at or after the deadline to trigger entry.
                if trade.entry_expires_at is not None:
                    now_utc_check = datetime.now(timezone.utc)
                    expires = trade.entry_expires_at
                    # Ensure timezone-aware comparison
                    if expires.tzinfo is None:
                        from datetime import timezone as _tz
                        expires = expires.replace(tzinfo=_tz.utc)
                    if now_utc_check >= expires:
                        logger.info(
                            f"[TRADE_MANAGER] Entry blocked for trade #{trade.id}: "
                            f"expired at {expires} (now={now_utc_check})"
                        )
                        continue

                # Trigger is based on entry bounds (Phase 10D)
                lower_bound = trade.entry_lower_bound if trade.entry_lower_bound is not None else float(signal.entry_trigger)
                upper_bound = trade.entry_upper_bound if trade.entry_upper_bound is not None else float(signal.entry_trigger)

                if lower_bound <= ltp <= upper_bound:
                    trade.status = TradeState.ENTRY_TRIGGERED
                    trade.actual_trigger_ltp = ltp
                    trade.actual_triggered_at = datetime.now(timezone.utc)
                    await self._log_trade_event(trade.id, "ENTRY_TRIGGERED", price=ltp)
                    # Create Entry Order (Paper)
                    sub = market_data_service.subscriptions.get(instrument_token, {})
                    qty = int(sub.get("lot_size", 75)) or 75
                    await self._place_paper_order(trade, "BUY", qty, ltp)
                    await self._update_position(trade, "BUY", qty, ltp)
                    
                    trade.status = TradeState.POSITION_OPEN
                    state_changed = True
                    await self._log_audit(trade.user_id, trade.id, "STATE_CHANGED", {"from": prev_state.value, "to": trade.status.value, "ltp": ltp, "trigger_zone": f"[{lower_bound}, {upper_bound}]"})

            elif trade.status in [TradeState.POSITION_OPEN, TradeState.PARTIAL_PROFIT, TradeState.TRAILING_STOP]:
                qty = trade.quantity
                if qty <= 0:
                    continue

                # 1. Hard Stop Loss
                if ltp <= signal.stop_loss:
                    broker_order = await self._place_paper_order(trade, "SELL", qty, ltp)
                    await self._update_position(trade, "SELL", qty, ltp)
                    trade.status = TradeState.CLOSED
                    trade.exit_triggered_at = datetime.now(timezone.utc)
                    trade.exit_reason = "STOP_LOSS"
                    trade.exit_quantity = qty
                    trade.exit_order_id = broker_order.broker_order_id if broker_order else None
                    state_changed = True
                    await self._log_trade_event(trade.id, "STOP_LOSS_TRIGGERED", price=ltp, quantity=qty)
                    await self._log_trade_event(trade.id, "TRADE_CLOSED", price=ltp)
                    await self._log_audit(trade.user_id, trade.id, "STOP_LOSS_TRIGGERED", {"price": ltp})
                    self._release_interest(trade)
                    
                # 2. Trailing Stop
                elif trade.trailing_active and trade.trailing_stop is not None and ltp <= trade.trailing_stop:
                    broker_order = await self._place_paper_order(trade, "SELL", qty, ltp)
                    await self._update_position(trade, "SELL", qty, ltp)
                    trade.status = TradeState.CLOSED
                    trade.exit_triggered_at = datetime.now(timezone.utc)
                    trade.exit_reason = "TRAILING_STOP"
                    trade.exit_quantity = qty
                    trade.exit_order_id = broker_order.broker_order_id if broker_order else None
                    trade.trailing_exit_ltp = ltp
                    trade.trailing_exit_at = datetime.now(timezone.utc)
                    state_changed = True
                    await self._log_trade_event(trade.id, "TRAILING_STOP_TRIGGERED", price=ltp, quantity=qty)
                    await self._log_trade_event(trade.id, "TRADE_CLOSED", price=ltp)
                    await self._log_audit(trade.user_id, trade.id, "TRAILING_STOP_TRIGGERED", {"price": ltp, "trailing_stop": trade.trailing_stop})
                    self._release_interest(trade)

                # 3. Partial Profit
                elif trade.partial_profit_enabled and not trade.partial_profit_taken and ltp >= (trade.entry_price + trade.partial_profit_trigger):
                    qty_to_exit = max(1, math.floor(qty * (trade.partial_profit_percentage / 100.0)))
                    
                    # Prevent exiting more than we have
                    qty_to_exit = min(qty_to_exit, qty)
                    
                    broker_order = await self._place_paper_order(trade, "SELL", qty_to_exit, ltp)
                    await self._update_position(trade, "SELL", qty_to_exit, ltp)
                    
                    trade.partial_profit_taken = True
                    trade.partial_profit_quantity = qty_to_exit
                    trade.partial_profit_ltp = ltp
                    trade.partial_profit_at = datetime.now(timezone.utc)
                    trade.partial_profit_order_id = broker_order.broker_order_id if broker_order else None
                    
                    trade.status = TradeState.PARTIAL_PROFIT
                    state_changed = True
                    await self._log_trade_event(trade.id, "PARTIAL_PROFIT_TRIGGERED", price=ltp, quantity=qty_to_exit)
                    await self._log_audit(trade.user_id, trade.id, "PARTIAL_PROFIT_TRIGGERED", {"price": ltp, "qty_exited": qty_to_exit})
                    
                    # If we sold everything (100% partial profit)
                    if trade.quantity <= 0:
                        trade.status = TradeState.CLOSED
                        trade.exit_triggered_at = datetime.now(timezone.utc)
                        trade.exit_reason = "PARTIAL_PROFIT" # Though normally target, we can log it here if 100% PP
                        await self._log_trade_event(trade.id, "TRADE_CLOSED", price=ltp)
                        self._release_interest(trade)

                # 4. Target
                elif ltp >= signal.target:
                    broker_order = await self._place_paper_order(trade, "SELL", trade.quantity, ltp)
                    await self._update_position(trade, "SELL", trade.quantity, ltp)
                    
                    trade.status = TradeState.CLOSED
                    trade.exit_triggered_at = datetime.now(timezone.utc)
                    trade.exit_reason = "TARGET"
                    trade.exit_quantity = qty
                    trade.exit_order_id = broker_order.broker_order_id if broker_order else None
                    state_changed = True
                    await self._log_trade_event(trade.id, "TARGET_TRIGGERED", price=ltp, quantity=trade.quantity)
                    await self._log_trade_event(trade.id, "TRADE_CLOSED", price=ltp)
                    await self._log_audit(trade.user_id, trade.id, "TARGET_TRIGGERED", {"price": ltp})
                    self._release_interest(trade)

                # 5. Trailing Update (No Exit)
                if trade.quantity > 0 and trade.trailing_stop_enabled:
                    # Check activation
                    if not trade.trailing_active:
                        activate = False
                        if trade.trailing_activation_mode == "AFTER_PARTIAL_PROFIT" and trade.partial_profit_taken:
                            activate = True
                        elif trade.trailing_activation_mode == "IMMEDIATE" and ltp >= (trade.entry_price + (trade.trailing_activation_profit or 0.0)):
                            activate = True
                            
                        if activate:
                            trade.trailing_active = True
                            trade.trailing_activated_at = datetime.now(timezone.utc)
                            trade.highest_ltp = ltp
                            trade.trailing_stop = max(signal.stop_loss, ltp - trade.trailing_distance)
                            trade.status = TradeState.TRAILING_STOP
                            state_changed = True
                            await self._log_trade_event(trade.id, "TRAILING_ACTIVATED", price=ltp, metadata={"trailing_stop": trade.trailing_stop, "mode": trade.trailing_activation_mode})
                            await self._log_audit(trade.user_id, trade.id, "TRAILING_STOP_ACTIVATED", {"price": ltp, "trailing_stop": trade.trailing_stop})
                    
                    # Update active trailing stop
                    if trade.trailing_active:
                        if ltp > (trade.highest_ltp or 0.0):
                            trade.highest_ltp = ltp
                            await self._log_trade_event(trade.id, "TRAILING_PEAK_UPDATED", price=ltp)
                            
                        new_stop = trade.highest_ltp - trade.trailing_distance
                        
                        # Trailing stop can only move up, and cannot drop below hard SL
                        current_stop = trade.trailing_stop if trade.trailing_stop is not None else signal.stop_loss
                        new_stop = max(new_stop, current_stop, signal.stop_loss)
                        
                        if new_stop > current_stop:
                            trade.trailing_stop = new_stop
                            trade.status = TradeState.TRAILING_STOP
                            state_changed = True
                            await self._log_trade_event(trade.id, "TRAILING_STOP_UPDATED", price=ltp, metadata={"new_stop": new_stop})
                                
            if state_changed:
                affected_trades.append({
                    "trade_id": trade.id,
                    "previous_state": prev_state.value,
                    "new_state": trade.status.value
                })
                
        if affected_trades:
            await self.db.commit()
            
        return affected_trades

    async def execute_manual_exit(self, message_type: TelegramMessageType, channel_id: str, timestamp: datetime, instrument_token: Optional[str] = None):
        """Handle Telegram EXIT or SL Hit or Partial Profit explicitly."""
        
        # Simple correlation: Find the most recent active trade
        # For a robust system, we correlate by channel_id and active state
        stmt = select(Trade).join(Signal).where(
            Trade.status.in_([TradeState.POSITION_OPEN, TradeState.PARTIAL_PROFIT, TradeState.TRAILING_STOP])
        ).order_by(Trade.created_at.desc())
        
        # In a real app we'd filter by channel_id, but our Trade table doesn't have it directly. 
        # We can join TelegramMessage.
        
        result = await self.db.execute(stmt)
        trades = result.scalars().all()
        
        if not trades:
            logger.info("No active trades found for exit message.")
            return
            
        trade = trades[0] # Best correlation for Phase 3
        ltp = await self.broker.get_ltp(trade.instrument_token)
        
        if message_type in [TelegramMessageType.EXIT, TelegramMessageType.STOP_LOSS]:
            qty = trade.quantity
            broker_order = None
            if qty > 0:
                broker_order = await self._place_paper_order(trade, "SELL", qty, ltp)
                await self._update_position(trade, "SELL", qty, ltp)
            trade.status = TradeState.CLOSED
            reason = "TELEGRAM_EXIT" if message_type == TelegramMessageType.EXIT else "TELEGRAM_SL_HIT"
            trade.exit_triggered_at = datetime.now(timezone.utc)
            trade.exit_reason = reason
            trade.exit_quantity = qty
            trade.exit_order_id = broker_order.broker_order_id if broker_order else None
            await self._log_trade_event(trade.id, "MANUAL_EXIT", price=ltp, quantity=qty, metadata={"reason": reason})
            await self._log_trade_event(trade.id, "TRADE_CLOSED", price=ltp)
            await self._log_audit(trade.user_id, trade.id, reason, {"price": ltp})
            self._release_interest(trade)
            
        elif message_type == TelegramMessageType.PARTIAL_PROFIT:
            if getattr(trade, 'partial_profit_enabled', False) and not getattr(trade, 'partial_profit_taken', False):
                qty_to_exit = max(1, math.floor(trade.quantity * (trade.partial_profit_percentage / 100.0)))
                qty_to_exit = min(qty_to_exit, trade.quantity)
                
                if qty_to_exit > 0:
                    broker_order = await self._place_paper_order(trade, "SELL", qty_to_exit, ltp)
                    await self._update_position(trade, "SELL", qty_to_exit, ltp)
                    trade.partial_profit_taken = True
                    trade.partial_profit_quantity = qty_to_exit
                    trade.partial_profit_ltp = ltp
                    trade.partial_profit_at = datetime.now(timezone.utc)
                    trade.partial_profit_order_id = broker_order.broker_order_id if broker_order else None
                    trade.status = TradeState.PARTIAL_PROFIT
                    await self._log_trade_event(trade.id, "PARTIAL_PROFIT_TRIGGERED", price=ltp, quantity=qty_to_exit, metadata={"reason": "MANUAL_PARTIAL_EXIT"})
                    await self._log_audit(trade.user_id, trade.id, "MANUAL_PARTIAL_EXIT", {"quantity": qty_to_exit, "price": ltp})
                    
                    if trade.quantity <= 0:
                        trade.status = TradeState.CLOSED
                        trade.exit_triggered_at = datetime.now(timezone.utc)
                        trade.exit_reason = "MANUAL_PARTIAL_EXIT"
                        await self._log_trade_event(trade.id, "TRADE_CLOSED", price=ltp)
                        self._release_interest(trade)
            else:
                logger.info("MANUAL_PARTIAL_EXIT_SKIPPED")
                
        await self.db.commit()

    async def cancel_waiting_signals(self) -> int:
        stmt = select(Trade).where(Trade.status == TradeState.WAITING_FOR_ENTRY)
        result = await self.db.execute(stmt)
        trades = result.scalars().all()
        
        count = 0
        for trade in trades:
            trade.status = TradeState.CANCELLED
            trade.cancel_reason = "MANUAL_CANCEL_WAITING"
            self._release_interest(trade)
            await self._log_trade_event(trade.id, "SIGNAL_ENTRY_TIMEOUT", metadata={"reason": "MANUAL_CANCEL_WAITING"})
            await self._log_audit(trade.user_id, trade.id, "WAITING_TRADE_CANCELLED_MANUAL", {"instrument": trade.instrument_token})
            count += 1
            
        if count > 0:
            await self.db.commit()
            logger.info(f"WAITING_TRADES_CANCELLED: {count}")
            
        return count

    async def emergency_close_all_paper_positions(self) -> dict:
        stmt = select(Trade).where(
            Trade.status.in_([TradeState.POSITION_OPEN, TradeState.PARTIAL_PROFIT, TradeState.TRAILING_STOP])
        )
        result = await self.db.execute(stmt)
        trades = result.scalars().all()
        
        closed_count = 0
        failed_count = 0
        total_pnl = 0.0
        
        from app.services.market_data_service import market_data_service
        
        for trade in trades:
            sub_info = market_data_service.subscriptions.get(trade.instrument_token, {})
            ltp = sub_info.get("latest_ltp")
            
            if ltp is None or ltp <= 0 or not math.isfinite(ltp):
                failed_count += 1
                await self._log_audit(trade.user_id, trade.id, "EMERGENCY_POSITION_CLOSE_FAILED", {"reason": "INVALID_LTP", "ltp": ltp})
                continue
                
            if trade.quantity > 0:
                try:
                    old_qty = trade.quantity
                    broker_order = await self._place_paper_order(trade, "SELL", trade.quantity, ltp)
                    await self._update_position(trade, "SELL", trade.quantity, ltp)
                    trade.status = TradeState.CLOSED
                    trade.exit_triggered_at = datetime.now(timezone.utc)
                    trade.exit_reason = "EMERGENCY_CLOSE"
                    trade.exit_quantity = old_qty
                    trade.exit_order_id = broker_order.broker_order_id if broker_order else None
                    self._release_interest(trade)
                    await self._log_trade_event(trade.id, "EMERGENCY_CLOSE", price=ltp, quantity=old_qty)
                    await self._log_trade_event(trade.id, "TRADE_CLOSED", price=ltp)
                    await self._log_audit(trade.user_id, trade.id, "EMERGENCY_POSITION_CLOSED", {"price": ltp, "quantity": old_qty})
                    
                    closed_count += 1
                    total_pnl += (trade.realized_pnl or 0.0)
                except Exception as e:
                    logger.error(f"Failed to emergency close trade {trade.id}: {e}")
                    failed_count += 1
                    await self._log_audit(trade.user_id, trade.id, "EMERGENCY_POSITION_CLOSE_FAILED", {"reason": str(e)})
                    
        if trades:
            await self.db.commit()
            
        return {
            "mode": "PAPER",
            "closed_positions": closed_count,
            "failed_positions": failed_count,
            "total_realized_pnl": total_pnl
        }
