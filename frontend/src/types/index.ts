export interface DashboardSummary {
  mode: string;
  live_orders: string;
  connections: {
    telegram: {
      status: string;
      channel: string;
      messages_received: number;
    };
    kotak: {
      status: string;
      read_only: boolean;
      last_request: string | null;
    };
    sfeed: {
      status: string;
      active_subscriptions: number;
      total_ticks: number;
      last_tick_time: string | null;
    };
    database: {
      status: string;
      type: string;
    };
  };
  metrics: {
    today_pnl: number;
    current_session_pnl?: number;
    historical_today_pnl?: number;
    active_trades: number;
    open_positions: number;
    signals_today: number;
    current_session_signals?: number;
    orders_today: number;
    current_session_orders?: number;
    historical_orders_today?: number;
    paper_session_id?: string | null;
    paper_reset_at?: string | null;
    new_trades_paused?: boolean;
  };
}

export interface TelegramUser {
  id: number;
  first_name: string;
  last_name: string;
  username: string;
  phone: string;
}

export interface TelegramChannelItem {
  channel_id: string;
  channel_name: string;
  username?: string | null;
  channel_type?: string | null;
  is_selected: boolean;
}

export interface TelegramStatus {
  enabled: boolean;
  connected: boolean;
  authenticated: boolean;
  connection_status?: string;
  authenticated_user: TelegramUser | null;
  listener_status: string;
  selected_channel: {
    channel_id: string;
    channel_name: string;
  } | null;
  last_message: string | null;
  last_message_time: string | null;
  last_message_sender?: string | null;
  messages_received: number;
  messages_parsed: number;
  messages_rejected: number;
  last_error: string | null;
}

export interface StoredTelegramMessage {
  id: number;
  telegram_message_id: string;
  channel_id: string;
  sender?: string | null;
  received_at: string | null;
  message_text: string;
  message_type: string;
  parsed_successfully: boolean;
  trade_id: number | null;
  processing_status: string;
  error_message: string | null;
}

export interface TradeSignalItem {
  id: number;
  timestamp: string | null;
  underlying: string;
  strike: number;
  option_type: string;
  expiry: string;
  entry_trigger: number;
  stop_loss: number;
  target: number;
  telegram_cmp: number | null;
  parser_status: string;
  trade_state: string;
  trade_id: number | null;
}

export interface TradeItem {
  id: number;
  signal_id: number;
  instrument: string;
  underlying: string;
  strike: number;
  option_type: string;
  expiry: string;
  entry_trigger: number;
  actual_entry: number | null;
  current_ltp: number | null;
  stop_loss: number;
  target: number;
  quantity: number;
  realized_pnl: number;
  status: string;
  cancel_reason?: string | null;
  entry_timeout_minutes: number | null;
  entry_expires_at?: string | null;
  entry_tolerance?: number | null;
  entry_direction?: string;
  entry_lower_bound?: number;
  entry_upper_bound?: number;
  actual_trigger_ltp?: number;
  actual_triggered_at?: string;
  created_at: string | null;
  updated_at: string | null;
}

export interface TimelineStep {
  step: number;
  title: string;
  completed: boolean;
  timestamp: string | null;
  details: Record<string, any>;
}

export interface TradeDetail {
  trade: {
    id: number;
    status: string;
    instrument: string;
    quantity: number;
    entry_price: number | null;
    exit_price: number | null;
    realized_pnl: number;
    created_at: string | null;
    updated_at: string | null;
  };
  signal: {
    underlying: string | null;
    strike: number | null;
    option_type: string | null;
    expiry: string | null;
    entry_trigger: number | null;
    stop_loss: number | null;
    target: number | null;
    telegram_cmp: number | null;
  };
  timeline: TimelineStep[];
  logs: Array<{
    id: number;
    action: string;
    details: any;
    timestamp: string | null;
  }>;
}

export interface PositionItem {
  id: number;
  trade_id: number;
  instrument: string;
  quantity: number;
  average_entry: number;
  current_ltp: number | null;
  unrealized_pnl: number;
  is_open: boolean;
  state: string;
  created_at: string | null;
}

export interface OrderItem {
  id: number;
  trade_id: number;
  broker_order_id: string;
  order_type: string;
  quantity: number;
  price: number;
  status: string;
  execution_type: string;
  is_paper: boolean;
  created_at: string | null;
}

export interface MarketSubscription {
  instrument_token: string;
  pSymbol: string;
  pExchSeg: string;
  pTrdSymbol: string;
  strike: number;
  option_type: string;
  expiry: string;
  latest_ltp: number | null;
  last_tick: string | null;
  feed_type: string;
  feed_status: string;
}

export interface BrokerStatus {
  broker_name: string;
  auth_status: string;
  trading_session: string;
  scrip_master: string;
  instrument_count: number;
  active_nifty_contracts: number;
  sfeed_status: string;
  read_only: boolean;
  live_orders: string;
  last_successful_request: string | null;
  profile: {
    client_code: string | null;
    account_status: string;
  } | null;
}

export interface BrokerFunds {
  available_margin: number;
  used_margin: number;
  available_cash: number;
  updated_at?: string;
  error?: boolean;
  message?: string;
}

export interface RiskConfig {
  max_daily_loss: number;
  max_risk_per_trade: number;
  max_trades_per_day: number;
  max_simultaneous_positions: number;
  daily_loss_protection_enabled: boolean;
  max_trades_protection_enabled: boolean;
  max_positions_protection_enabled: boolean;
  is_algo_active: boolean;
  entry_timeout_minutes: number;
  entry_tolerance: number;
  quantity_mode: string;
  fixed_lots: number;
  partial_profit_enabled: boolean;
  partial_profit_trigger: number;
  partial_profit_percentage: number;
  trailing_stop_enabled: boolean;
  trailing_activation_mode: string;
  trailing_activation_profit: number | null;
  trailing_distance: number;
  updated_at?: string | null;
}

export interface UpdateRiskConfigRequest {
  max_daily_loss: number;
  max_risk_per_trade: number;
  max_trades_per_day: number;
  max_simultaneous_positions: number;
  daily_loss_protection_enabled?: boolean;
  max_trades_protection_enabled?: boolean;
  max_positions_protection_enabled?: boolean;
  is_algo_active?: boolean;
  entry_timeout_minutes?: number;
  entry_tolerance?: number;
  quantity_mode?: string;
  fixed_lots?: number;
  partial_profit_enabled?: boolean;
  partial_profit_trigger?: number;
  partial_profit_percentage?: number;
  trailing_stop_enabled?: boolean;
  trailing_activation_mode?: string;
  trailing_activation_profit?: number | null;
  trailing_distance?: number;
}

export interface RiskStatus {
  limits: {
    max_daily_loss: number;
    max_risk_per_trade?: number;
    max_trades_per_day: number;
    max_simultaneous_positions: number;
    daily_loss_protection_enabled?: boolean;
    max_trades_protection_enabled?: boolean;
    max_positions_protection_enabled?: boolean;
    partial_exit_percent: number;
    trailing_enabled: boolean;
    trailing_distance: number;
    is_algo_active: boolean;
  };
  current: {
    trades_today: number;
    trades_used?: number;
    trades_remaining?: number;
    risk_scope?: string;
    open_positions: number;
    realized_pnl: number;
    remaining_daily_loss_allowance?: number;
    new_trades_allowed?: boolean;
    active_rejection_reason?: string | null;
    risk_status: string;
  };
}

export interface AuditLogItem {
  id: number;
  timestamp: string | null;
  event: string;
  trade_id: number | null;
  severity: string;
  description: string;
}

export interface TradingStatusResponse {
  session_date: string;
  mode: string;
  daily_pnl: number;
  daily_trade_count: number;
  active_trades: number;
  open_positions: number;
  waiting_signals: number;
  partial_profit_positions: number;
  trailing_positions: number;
  max_daily_loss: number;
  daily_loss_limit_reached: boolean;
  new_trades_paused: boolean;
}

export interface TradeEventItem {
  id: number;
  trade_id: number;
  event_type: string;
  timestamp: string | null;
  price: number | null;
  quantity: number | null;
  metadata_json: Record<string, any> | null;
}

export interface AnalyticsSummary {
  period_days: number;
  total_closed_trades: number;
  winning_trades: number;
  losing_trades: number;
  win_rate_percentage: number;
  total_realized_pnl: number;
}

export interface DailyAnalytics {
  date: string;
  pnl: number;
}
