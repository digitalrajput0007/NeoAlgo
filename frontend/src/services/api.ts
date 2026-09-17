import type {
  DashboardSummary,
  TelegramStatus,
  StoredTelegramMessage,
  TradeSignalItem,
  TradeItem,
  TradeDetail,
  PositionItem,
  OrderItem,
  MarketSubscription,
  BrokerStatus,
  RiskStatus,
  RiskConfig,
  UpdateRiskConfigRequest,
  AuditLogItem,
  TradingModeConfig
} from '../types';

const API_BASE = 'http://localhost:8000/api';

// Helper function to handle fetch and 401 unauthorized
async function fetchWithAuth(url: string, options: RequestInit = {}): Promise<Response> {
  const mergedOptions = {
    ...options,
    credentials: 'include' as RequestCredentials,
  };
  const res = await fetch(url, mergedOptions);
  
  if (res.status === 401) {
    // Emit global logout event to reset context
    window.dispatchEvent(new Event('auth:logout'));
    throw new Error('Unauthorized');
  }
  
  return res;
}

export const api = {
  // --- Auth (Phase 11C) ---
  async loginAdmin(username: string, password: string): Promise<any> {
    const res = await fetchWithAuth(`${API_BASE}/auth/login`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ username, password }),
    });
    if (!res.ok) {
      const err = new Error('Login failed') as any;
      err.response = { status: res.status };
      throw err;
    }
    return res.json();
  },

  async logoutAdmin(): Promise<any> {
    const res = await fetchWithAuth(`${API_BASE}/auth/logout`, {
      method: 'POST',
    });
    if (!res.ok) throw new Error('Logout failed');
    return res.json();
  },

  async checkAuthStatus(): Promise<{ authenticated: boolean; username: string }> {
    const res = await fetchWithAuth(`${API_BASE}/auth/status`);
    if (!res.ok) throw new Error('Not authenticated');
    return res.json();
  },

  // --- Profile (Phase 11E) ---
  async getProfile(): Promise<{ display_name: string; username: string; role_label: string; avatar_url: string | null }> {
    const res = await fetchWithAuth(`${API_BASE}/profile`);
    if (!res.ok) throw new Error('Failed to fetch profile');
    return res.json();
  },

  async updateProfile(display_name: string): Promise<any> {
    const res = await fetchWithAuth(`${API_BASE}/profile`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ display_name }),
    });
    if (!res.ok) throw new Error('Failed to update profile');
    return res.json();
  },

  async uploadAvatar(file: File): Promise<any> {
    const formData = new FormData();
    formData.append('file', file);
    // Note: Do not set Content-Type header when sending FormData, browser sets it with boundary
    const res = await fetchWithAuth(`${API_BASE}/profile/avatar`, {
      method: 'POST',
      body: formData,
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail || 'Failed to upload avatar');
    }
    return res.json();
  },

  async removeAvatar(): Promise<any> {
    const res = await fetchWithAuth(`${API_BASE}/profile/avatar`, {
      method: 'DELETE',
    });
    if (!res.ok) throw new Error('Failed to remove avatar');
    return res.json();
  },

  async changePassword(data: { current_password: string; new_password: string }): Promise<any> {
    const res = await fetchWithAuth(`${API_BASE}/profile/password`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(data)
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail || 'Failed to change password');
    }
    return res.json();
  },

  // --- App ---
  async getDashboardSummary(): Promise<DashboardSummary> {
    const res = await fetchWithAuth(`${API_BASE}/dashboard/summary`);
    if (!res.ok) throw new Error('Failed to fetch dashboard summary');
    return res.json();
  },

  async getTelegramStatus(): Promise<TelegramStatus> {
    const res = await fetchWithAuth(`${API_BASE}/telegram/status`);
    if (!res.ok) throw new Error('Failed to fetch telegram status');
    return res.json();
  },

  async getTelegramChannels(): Promise<import('../types').TelegramChannelItem[]> {
    const res = await fetchWithAuth(`${API_BASE}/telegram/channels`);
    if (!res.ok) throw new Error('Failed to fetch telegram channels');
    return res.json();
  },

  async selectTelegramChannel(channel_id: string, channel_name?: string): Promise<any> {
    const res = await fetchWithAuth(`${API_BASE}/telegram/channels/select`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ channel_id, channel_name }),
    });
    if (!res.ok) throw new Error('Failed to select telegram channel');
    return res.json();
  },

  async connectTelegram(): Promise<any> {
    const res = await fetchWithAuth(`${API_BASE}/telegram/connect`, { method: 'POST' });
    if (!res.ok) throw new Error('Failed to connect telegram');
    return res.json();
  },

  async disconnectTelegram(): Promise<any> {
    const res = await fetchWithAuth(`${API_BASE}/telegram/disconnect`, { method: 'POST' });
    if (!res.ok) throw new Error('Failed to disconnect telegram');
    return res.json();
  },

  async reconnectTelegram(): Promise<any> {
    const res = await fetchWithAuth(`${API_BASE}/telegram/reconnect`, { method: 'POST' });
    if (!res.ok) throw new Error('Failed to reconnect telegram');
    return res.json();
  },

  async sendTelegramCode(phone: string): Promise<any> {
    const res = await fetchWithAuth(`${API_BASE}/telegram/auth/send-code`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ phone }),
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail || 'Failed to send login code');
    }
    return res.json();
  },

  async signInTelegram(phone: string, code: string, password?: string): Promise<any> {
    const res = await fetchWithAuth(`${API_BASE}/telegram/auth/sign-in`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ phone, code, password }),
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail || 'Failed to sign in');
    }
    return res.json();
  },

  async logoutTelegram(): Promise<any> {
    const res = await fetchWithAuth(`${API_BASE}/telegram/auth/logout`, {
      method: 'POST',
    });
    if (!res.ok) throw new Error('Failed to logout');
    return res.json();
  },

  async getTelegramMessages(): Promise<StoredTelegramMessage[]> {
    const res = await fetchWithAuth(`${API_BASE}/telegram/messages`);
    if (!res.ok) throw new Error('Failed to fetch telegram messages');
    return res.json();
  },

  async getSignals(): Promise<TradeSignalItem[]> {
    const res = await fetchWithAuth(`${API_BASE}/signals`);
    if (!res.ok) throw new Error('Failed to fetch signals');
    return res.json();
  },

  async getTrades(scope?: string): Promise<TradeItem[]> {
    const url = scope ? `${API_BASE}/trades?scope=${encodeURIComponent(scope)}` : `${API_BASE}/trades`;
    const res = await fetchWithAuth(url);
    if (!res.ok) throw new Error('Failed to fetch trades');
    return res.json();
  },

  async getTradeDetail(tradeId: number): Promise<TradeDetail> {
    const res = await fetchWithAuth(`${API_BASE}/trades/${tradeId}`);
    if (!res.ok) throw new Error('Failed to fetch trade detail');
    return res.json();
  },

  async getPositions(scope?: string): Promise<PositionItem[]> {
    const url = scope ? `${API_BASE}/positions?scope=${encodeURIComponent(scope)}` : `${API_BASE}/positions`;
    const res = await fetchWithAuth(url);
    if (!res.ok) throw new Error('Failed to fetch positions');
    return res.json();
  },

  async getOrders(scope?: string): Promise<OrderItem[]> {
    const url = scope ? `${API_BASE}/orders?scope=${encodeURIComponent(scope)}` : `${API_BASE}/orders`;
    const res = await fetchWithAuth(url);
    if (!res.ok) throw new Error('Failed to fetch orders');
    return res.json();
  },

  async getMarketSubscriptions(): Promise<MarketSubscription[]> {
    const res = await fetchWithAuth(`${API_BASE}/market-data/subscriptions`);
    if (!res.ok) throw new Error('Failed to fetch market subscriptions');
    return res.json();
  },

  async getBrokerStatus(): Promise<BrokerStatus> {
    const res = await fetchWithAuth(`${API_BASE}/broker/status`);
    if (!res.ok) throw new Error('Failed to fetch broker status');
    return res.json();
  },

  async getBrokerAccountLimits(refresh: boolean = false): Promise<any> {
    const res = await fetchWithAuth(`${API_BASE}/broker/account-limits?refresh=${refresh}`);
    if (!res.ok) throw new Error('Failed to fetch broker account limits');
    return res.json();
  },

  async getRiskStatus(): Promise<RiskStatus> {
    const res = await fetchWithAuth(`${API_BASE}/risk/status`);
    if (!res.ok) throw new Error('Failed to fetch risk status');
    return res.json();
  },

  async getRiskConfig(): Promise<RiskConfig> {
    const res = await fetchWithAuth(`${API_BASE}/risk/config`);
    if (!res.ok) throw new Error('Failed to fetch risk configuration');
    return res.json();
  },

  async updateRiskConfig(config: UpdateRiskConfigRequest): Promise<{ status: string; message: string; config: RiskConfig }> {
    const res = await fetchWithAuth(`${API_BASE}/risk/config`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(config),
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail || 'Failed to update risk configuration');
    }
    return res.json();
  },

  async getAuditLogs(): Promise<AuditLogItem[]> {
    const res = await fetchWithAuth(`${API_BASE}/audit-logs`);
    if (!res.ok) throw new Error('Failed to fetch audit logs');
    return res.json();
  },

  async simulateSignal(data: {
    underlying: string;
    strike: number;
    option_type: string;
    expiry: string;
    entry_trigger: number;
    stop_loss: number;
    target: number;
  }): Promise<any> {
    const res = await fetchWithAuth(`${API_BASE}/paper/simulate-signal`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(data),
    });
    if (!res.ok) throw new Error('Failed to simulate signal');
    return res.json();
  },

  async injectPrice(instrument: string, price: number): Promise<any> {
    const res = await fetchWithAuth(`${API_BASE}/paper/inject-price`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ instrument, price }),
    });
    if (!res.ok) throw new Error('Failed to inject test price');
    return res.json();
  },

  async resetPaperState(): Promise<{
    status: string;
    message: string;
    open_positions_before_reset: number;
    positions_reset: number;
    paper_trades_reset_closed: number;
    live_broker_positions_touched: number;
    live_orders: string;
  }> {
    const res = await fetchWithAuth(`${API_BASE}/paper/reset`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: 'Failed to reset paper state' }));
      throw new Error(err.detail || 'Failed to reset paper state');
    }
    return res.json();
  },

  // Trading Controls (Phase 10F)
  async getTradingStatus(): Promise<import('../types').TradingStatusResponse> {
    const res = await fetchWithAuth(`${API_BASE}/trading/status`);
    if (!res.ok) throw new Error('Failed to fetch trading status');
    return res.json();
  },

  async pauseNewTrades(): Promise<any> {
    const res = await fetchWithAuth(`${API_BASE}/trading/pause`, { method: 'POST' });
    if (!res.ok) throw new Error('Failed to pause trading');
    return res.json();
  },

  async resumeNewTrades(): Promise<any> {
    const res = await fetchWithAuth(`${API_BASE}/trading/resume`, { method: 'POST' });
    if (!res.ok) throw new Error('Failed to resume trading');
    return res.json();
  },

  async cancelWaitingSignals(): Promise<any> {
    const res = await fetchWithAuth(`${API_BASE}/trading/cancel-waiting`, { method: 'POST' });
    if (!res.ok) throw new Error('Failed to cancel waiting signals');
    return res.json();
  },

  async emergencyCloseAll(): Promise<any> {
    const res = await fetchWithAuth(`${API_BASE}/trading/emergency-close`, { method: 'POST' });
    if (!res.ok) throw new Error('Failed to emergency close positions');
    return res.json();
  },

  // Journal and Analytics (Phase 10G)
  async getJournalTrades(skip: number = 0, limit: number = 50, status?: string, underlying?: string): Promise<any> {
    const params = new URLSearchParams({
      skip: skip.toString(),
      limit: limit.toString(),
    });
    if (status) params.append('status', status);
    if (underlying) params.append('underlying', underlying);
    
    const res = await fetchWithAuth(`${API_BASE}/journal/trades?${params.toString()}`);
    if (!res.ok) throw new Error('Failed to fetch journal trades');
    return res.json();
  },

  async getJournalTrade(tradeId: number): Promise<import('../types').TradeItem> {
    const res = await fetchWithAuth(`${API_BASE}/journal/trades/${tradeId}`);
    if (!res.ok) throw new Error('Failed to fetch trade details');
    return res.json();
  },

  async getJournalTradeEvents(tradeId: number): Promise<import('../types').TradeEventItem[]> {
    const res = await fetchWithAuth(`${API_BASE}/journal/trades/${tradeId}/events`);
    if (!res.ok) throw new Error('Failed to fetch trade events');
    return res.json();
  },

  async getAnalytics(days: number = 30): Promise<import('../types').AnalyticsSummary> {
    const res = await fetchWithAuth(`${API_BASE}/journal/analytics?days=${days}`);
    if (!res.ok) throw new Error('Failed to fetch analytics');
    return res.json();
  },

  async getDailyAnalytics(days: number = 30): Promise<import('../types').DailyAnalytics[]> {
    const res = await fetchWithAuth(`${API_BASE}/journal/analytics/daily?days=${days}`);
    if (!res.ok) throw new Error('Failed to fetch daily analytics');
    return res.json();
  },

  async getMarketOverview(): Promise<import('../types').MarketOverviewData> {
    const res = await fetchWithAuth(`${API_BASE}/dashboard/market-overview`);
    if (!res.ok) throw new Error('Failed to fetch market overview');
    return res.json();
  },

  async getTradingMode(): Promise<TradingModeConfig> {
    const res = await fetchWithAuth(`${API_BASE}/trading/mode`);
    if (!res.ok) throw new Error('Failed to fetch trading mode');
    return res.json();
  },

  async setTradingMode(mode: string, live_trading_enabled: boolean, confirmation: boolean): Promise<TradingModeConfig> {
    const res = await fetchWithAuth(`${API_BASE}/trading/mode`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json'
      },
      body: JSON.stringify({ mode, live_trading_enabled, confirmation })
    });
    if (!res.ok) {
      const data = await res.json().catch(() => ({}));
      throw new Error(data.detail || 'Failed to update trading mode');
    }
    return res.json();
  },
};
