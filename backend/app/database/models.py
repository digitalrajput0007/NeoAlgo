from sqlalchemy import Column, Integer, String, Boolean, DateTime, Float, ForeignKey, JSON, Enum, UniqueConstraint
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
import enum
from app.database.database import Base

class TradeState(str, enum.Enum):
    NEW_SIGNAL = "NEW_SIGNAL"
    WAITING_FOR_ENTRY = "WAITING_FOR_ENTRY"
    ENTRY_TRIGGERED = "ENTRY_TRIGGERED"
    ENTRY_ORDER_PENDING = "ENTRY_ORDER_PENDING"
    POSITION_OPEN = "POSITION_OPEN"
    PARTIAL_PROFIT = "PARTIAL_PROFIT"
    TRAILING_STOP = "TRAILING_STOP"
    EXIT_PENDING = "EXIT_PENDING"
    CLOSED = "CLOSED"
    CANCELLED = "CANCELLED"
    REJECTED = "REJECTED"
    ERROR = "ERROR"

class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, index=True)
    email = Column(String, unique=True, index=True)
    hashed_password = Column(String)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    broker_accounts = relationship("BrokerAccount", back_populates="user")
    trading_settings = relationship("TradingSettings", back_populates="user", uselist=False)

class BrokerAccount(Base):
    __tablename__ = "broker_accounts"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    broker_name = Column(String)
    api_key = Column(String, nullable=True)
    api_secret = Column(String, nullable=True)
    access_token = Column(String, nullable=True)
    is_paper_trading = Column(Boolean, default=True)
    paper_session_id = Column(String, nullable=True)
    paper_reset_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    user = relationship("User", back_populates="broker_accounts")

class TradingSettings(Base):
    __tablename__ = "trading_settings"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), unique=True, nullable=True)
    max_daily_loss = Column(Float, default=6000.0)
    max_risk_per_trade = Column(Float, default=2000.0)
    max_trades_per_day = Column(Integer, default=5)
    max_simultaneous_positions = Column(Integer, default=2)
    daily_loss_protection_enabled = Column(Boolean, default=True)
    max_trades_protection_enabled = Column(Boolean, default=True)
    max_positions_protection_enabled = Column(Boolean, default=True)
    
    # Phase 12 Configs
    quantity_mode = Column(String, default="FIXED")
    fixed_lots = Column(Integer, default=1)
    
    # Phase 10E Configs
    partial_profit_enabled = Column(Boolean, default=False)
    partial_profit_trigger = Column(Float, default=10.00)
    partial_profit_percentage = Column(Float, default=50.0)
    
    trailing_stop_enabled = Column(Boolean, default=False)
    trailing_activation_mode = Column(String, default="AFTER_PARTIAL_PROFIT")
    trailing_activation_profit = Column(Float, default=10.00)
    trailing_distance = Column(Float, default=5.00)
    
    is_algo_active = Column(Boolean, default=True)
    new_trades_paused = Column(Boolean, default=False)
    entry_timeout_minutes = Column(Integer, default=15)
    entry_tolerance = Column(Float, nullable=True, default=1.0)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    
    user = relationship("User", back_populates="trading_settings")

class TelegramChannel(Base):
    __tablename__ = "telegram_channels"
    id = Column(Integer, primary_key=True, index=True)
    channel_id = Column(String, unique=True, index=True)
    channel_name = Column(String)
    username = Column(String, nullable=True)
    channel_type = Column(String, nullable=True) # broadcast, megagroup, chat
    is_selected = Column(Boolean, default=False)
    is_active = Column(Boolean, default=True)

class TelegramMessage(Base):
    __tablename__ = "telegram_messages"
    id = Column(Integer, primary_key=True, index=True)
    telegram_message_id = Column(String, index=True)
    channel_id = Column(String, ForeignKey("telegram_channels.channel_id"), nullable=True)
    sender = Column(String, nullable=True)
    received_at = Column(DateTime(timezone=True), server_default=func.now())
    message_text = Column(String)
    message_type = Column(String)
    parsed_successfully = Column(Boolean, default=False)
    trade_id = Column(Integer, ForeignKey("trades.id"), nullable=True)
    processing_status = Column(String)
    error_message = Column(String, nullable=True)

    __table_args__ = (
        UniqueConstraint('telegram_message_id', 'channel_id', name='uq_telegram_msg_channel'),
    )

class Signal(Base):
    __tablename__ = "signals"
    id = Column(Integer, primary_key=True, index=True)
    message_id = Column(Integer, ForeignKey("telegram_messages.id"))
    underlying = Column(String)
    strike = Column(Float)
    option_type = Column(String)
    expiry = Column(String)
    entry_trigger = Column(Float)
    stop_loss = Column(Float)
    target = Column(Float)
    telegram_cmp = Column(Float)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

class Trade(Base):
    __tablename__ = "trades"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    signal_id = Column(Integer, ForeignKey("signals.id"))
    broker_account_id = Column(Integer, ForeignKey("broker_accounts.id"))
    status = Column(Enum(TradeState), default=TradeState.NEW_SIGNAL)
    instrument_token = Column(String, nullable=True)
    quantity = Column(Integer, default=0)
    entry_price = Column(Float, nullable=True)
    exit_price = Column(Float, nullable=True)
    realized_pnl = Column(Float, default=0.0)
    risk_snapshot = Column(JSON, nullable=True)
    entry_timeout_minutes = Column(Integer, nullable=True)        # snapshot of configured timeout at creation
    entry_expires_at = Column(DateTime(timezone=True), nullable=True)  # frozen expiry timestamp
    entry_tolerance = Column(Float, nullable=True)
    entry_direction = Column(String, nullable=True)               # "ABOVE" or "BELOW"
    entry_lower_bound = Column(Float, nullable=True)
    entry_upper_bound = Column(Float, nullable=True)
    actual_trigger_ltp = Column(Float, nullable=True)
    actual_triggered_at = Column(DateTime(timezone=True), nullable=True)
    
    # Phase 10E: Partial Profit and Trailing Stop configurations (snapshotted)
    partial_profit_enabled = Column(Boolean, default=False)
    partial_profit_trigger = Column(Float, nullable=True)
    partial_profit_percentage = Column(Float, nullable=True)
    partial_profit_taken = Column(Boolean, default=False)
    
    trailing_stop_enabled = Column(Boolean, default=False)
    trailing_activation_mode = Column(String, nullable=True)
    trailing_activation_profit = Column(Float, nullable=True)
    trailing_distance = Column(Float, nullable=True)
    
    trailing_active = Column(Boolean, default=False)
    highest_ltp = Column(Float, nullable=True)
    trailing_stop = Column(Float, nullable=True)
    trailing_activated_at = Column(DateTime(timezone=True), nullable=True)

    cancel_reason = Column(String, nullable=True)                 # e.g. SIGNAL_ENTRY_TIMEOUT
    
    # Phase 10G: Journal and Exit metrics
    entry_order_id = Column(String, nullable=True)
    exit_order_id = Column(String, nullable=True)
    exit_triggered_at = Column(DateTime(timezone=True), nullable=True)
    exit_quantity = Column(Integer, default=0)
    exit_reason = Column(String, nullable=True)
    partial_profit_quantity = Column(Integer, default=0)
    partial_profit_ltp = Column(Float, nullable=True)
    partial_profit_at = Column(DateTime(timezone=True), nullable=True)
    partial_profit_order_id = Column(String, nullable=True)
    trailing_exit_ltp = Column(Float, nullable=True)
    trailing_exit_at = Column(DateTime(timezone=True), nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

class TradeEvent(Base):
    __tablename__ = "trade_events"
    id = Column(Integer, primary_key=True, index=True)
    trade_id = Column(Integer, ForeignKey("trades.id"))
    event_type = Column(String, index=True)
    timestamp = Column(DateTime(timezone=True), server_default=func.now())
    price = Column(Float, nullable=True)
    quantity = Column(Integer, nullable=True)
    metadata_json = Column(JSON, nullable=True)

class Order(Base):
    __tablename__ = "orders"
    id = Column(Integer, primary_key=True, index=True)
    trade_id = Column(Integer, ForeignKey("trades.id"))
    broker_order_id = Column(String, index=True)
    order_type = Column(String) # BUY / SELL
    quantity = Column(Integer)
    price = Column(Float)
    status = Column(String)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

class Position(Base):
    __tablename__ = "positions"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    trade_id = Column(Integer, ForeignKey("trades.id"))
    broker_account_id = Column(Integer, ForeignKey("broker_accounts.id"))
    instrument_token = Column(String)
    quantity = Column(Integer)
    average_price = Column(Float)
    is_open = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

class RiskEvent(Base):
    __tablename__ = "risk_events"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    trade_id = Column(Integer, ForeignKey("trades.id"), nullable=True)
    event_type = Column(String)
    description = Column(String)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

class AuditLog(Base):
    __tablename__ = "audit_logs"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    action = Column(String)
    details = Column(JSON)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
