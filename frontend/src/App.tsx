import { useEffect, useState, useCallback, useRef } from 'react';
import { useLocation, Routes, Route, Navigate, Outlet } from 'react-router-dom';
import { api } from './services/api';
import type {
  DashboardSummary,
  TelegramStatus,
  StoredTelegramMessage,
  TelegramChannelItem,
  TradeSignalItem,
  TradeItem,
  TradeDetail,
  PositionItem,
  OrderItem,
  MarketSubscription,
  BrokerStatus,
  RiskStatus,
  RiskConfig,
  AuditLogItem
} from './types';
import { TradeDetailDrawer } from './components/trading/TradeDetailDrawer';
import { Journal } from './components/Journal';
import { formatLocalTime, formatLocalDateTime } from './utils/timezone';

import { AppShell } from './components/layout/AppShell';
import { DashboardOverview } from './components/dashboard/DashboardOverview';
import { MarketDataCard } from './components/market/MarketDataCard';
import { OperationalControls } from './components/controls/OperationalControls';
import { SystemHealthPage } from './pages/SystemHealthPage';
import { AuditLogsPage } from './pages/AuditLogsPage';
import { BrokerPage } from './pages/BrokerPage';
import { SignalsTab } from './components/trading/SignalsTab';
import { TradesTab } from './components/trading/TradesTab';
import { PositionsTab } from './components/trading/PositionsTab';
import { OrdersTab } from './components/trading/OrdersTab';
import { RiskManagementTab } from './components/risk/RiskManagementTab';
import { TelegramPage } from './pages/TelegramPage';
import { ChannelSelectorDialog } from './components/telegram/ChannelSelectorDialog';
import { useAuth } from './contexts/AuthContext';
import { ProtectedRoute } from './components/ProtectedRoute';
import { LoginPage } from './pages/LoginPage';
import { CircularProgress, Box } from '@mui/material';


function getExpiryCountdown(expiresAt: string | null | undefined): string | null {
  if (!expiresAt) return null;
  const now = new Date();
  const exp = new Date(expiresAt);
  const diffMs = exp.getTime() - now.getTime();
  if (diffMs <= 0) return 'Expired';
  const mins = Math.floor(diffMs / 60000);
  const secs = Math.floor((diffMs % 60000) / 1000).toString().padStart(2, '0');
  return `${mins}:${secs}`;
}

export function App() {
  const location = useLocation();
  const activeTab = location.pathname === '/' ? 'dashboard' : location.pathname.replace('/', '');
  const [lastRefreshed, setLastRefreshed] = useState<string>('');
  
  // Data states
  const [summary, setSummary] = useState<DashboardSummary | null>(null);
  const [signals, setSignals] = useState<TradeSignalItem[]>([]);
  const [trades, setTrades] = useState<TradeItem[]>([]);
  const [historyTrades, setHistoryTrades] = useState<TradeItem[]>([]);
  const [positions, setPositions] = useState<PositionItem[]>([]);
  const [historyPositions, setHistoryPositions] = useState<PositionItem[]>([]);
  const [orders, setOrders] = useState<OrderItem[]>([]);
  const [historyOrders, setHistoryOrders] = useState<OrderItem[]>([]);

  // Auth Context
  const { authenticated, loading: authLoading } = useAuth();

  // Sub-tab view selections

  const [tradesView, setTradesView] = useState<'active' | 'history'>('active');
  const [positionsView, setPositionsView] = useState<'open' | 'history'>('open');
  const [ordersView, setOrdersView] = useState<'current' | 'history'>('current');

  const [telegramStatus, setTelegramStatus] = useState<TelegramStatus | null>(null);
  const [telegramMessages, setTelegramMessages] = useState<StoredTelegramMessage[]>([]);
  const [telegramChannels, setTelegramChannels] = useState<TelegramChannelItem[]>([]);
  const [marketSubs, setMarketSubs] = useState<MarketSubscription[]>([]);
  const [brokerStatus, setBrokerStatus] = useState<BrokerStatus | null>(null);
  const [riskStatus, setRiskStatus] = useState<RiskStatus | null>(null);
  const [riskConfig, setRiskConfig] = useState<RiskConfig | null>(null);
  const [formDailyLoss, setFormDailyLoss] = useState('6000');
  const [formRiskPerTrade, setFormRiskPerTrade] = useState('2000');
  const [formMaxTrades, setFormMaxTrades] = useState('5');
  const [formMaxPositions, setFormMaxPositions] = useState('2');
  const [formQuantityMode, setFormQuantityMode] = useState('FIXED');
  const [formFixedLots, setFormFixedLots] = useState('1');
  const [formEntryTimeout, setFormEntryTimeout] = useState('15');
  const [formEntryTolerance, setFormEntryTolerance] = useState('1.0');
  const [formDailyLossEnabled, setFormDailyLossEnabled] = useState(true);
  const [formMaxTradesEnabled, setFormMaxTradesEnabled] = useState(true);
  const [formMaxPositionsEnabled, setFormMaxPositionsEnabled] = useState(true);
  const [formPartialProfitEnabled, setFormPartialProfitEnabled] = useState(false);
  const [formPartialProfitTrigger, setFormPartialProfitTrigger] = useState('10.0');
  const [formPartialProfitPercentage, setFormPartialProfitPercentage] = useState('50');
  const [formTrailingStopEnabled, setFormTrailingStopEnabled] = useState(false);
  const [formTrailingMode, setFormTrailingMode] = useState('AFTER_PARTIAL_PROFIT');
  const [formTrailingActivationProfit, setFormTrailingActivationProfit] = useState('10.0');
  const [formTrailingDistance, setFormTrailingDistance] = useState('5.0');
  const [riskSaving, setRiskSaving] = useState(false);
  const [riskMsg, setRiskMsg] = useState<{ type: 'success' | 'error'; text: string } | null>(null);
  const [auditLogs, setAuditLogs] = useState<AuditLogItem[]>([]);

  // Telegram Auth & Channel State
  const [authPhone, setAuthPhone] = useState('');
  const [authCode, setAuthCode] = useState('');
  const [authPassword, setAuthPassword] = useState('');
  const [authStep, setAuthStep] = useState<'phone' | 'code'>('phone');
  const [telegramAuthLoading, setTelegramAuthLoading] = useState(false);
  const [authMsg, setAuthMsg] = useState<{ type: 'success' | 'error'; text: string } | null>(null);
  const [selectingChannelId, setSelectingChannelId] = useState<string | null>(null);
  const [showChannelSelector, setShowChannelSelector] = useState(false);

  // Modal state
  const [selectedTradeDetail, setSelectedTradeDetail] = useState<TradeDetail | null>(null);
  const [detailLoading, setDetailLoading] = useState<boolean>(false);

  // Simulator Form State
  const [simUnderlying, setSimUnderlying] = useState('NIFTY');
  const [simStrike, setSimStrike] = useState('23500');
  const [simOptionType, setSimOptionType] = useState('CE');
  const [simExpiry, setSimExpiry] = useState('2026-09-15');
  const [simEntry, setSimEntry] = useState('150.0');
  const [simSL, setSimSL] = useState('144.0');
  const [simTarget, setSimTarget] = useState('170.0');
  const [simStatus, setSimStatus] = useState<any>(null);
  const [simSubmitting, setSimSubmitting] = useState(false);

  // Trading Controls State
  const [tradingStatus, setTradingStatus] = useState<any>(null);
  const [tradingActionLoading, setTradingActionLoading] = useState<string | null>(null);
  const [showEmergencyModal, setShowEmergencyModal] = useState(false);
  const [emergencyResult, setEmergencyResult] = useState<any>(null);

  // Market Data Injector State
  const [injectToken, setInjectToken] = useState('PAPER_NIFTY_23500_CE_2026-09-15');
  const [injectPrice, setInjectPrice] = useState('152.0');
  const [injectStatus, setInjectStatus] = useState<any>(null);
  const [injectSubmitting, setInjectSubmitting] = useState(false);

  // Paper State Reset Control
  const [showResetModal, setShowResetModal] = useState(false);
  const [resettingPaper, setResettingPaper] = useState(false);
  const [resetAlert, setResetAlert] = useState<{ type: 'success' | 'error'; message: string } | null>(null);



  // Realtime Data Fetch (400ms interval for active trades & market data)
  const isFetchingRealtime = useRef(false);
  const fetchRealtimeData = useCallback(async () => {
    if (isFetchingRealtime.current) return;
    isFetchingRealtime.current = true;
    try {
      const [trdActive, mkt] = await Promise.allSettled([
        api.getTrades('active'),
        api.getMarketSubscriptions(),
      ]);

      if (trdActive.status === 'fulfilled') setTrades(trdActive.value);
      if (mkt.status === 'fulfilled') setMarketSubs(mkt.value);
      setLastRefreshed(formatLocalTime(new Date()));
    } catch (err: any) {
      console.error('Realtime polling error:', err);
    } finally {
      isFetchingRealtime.current = false;
    }
  }, []);

  // Slow Data Fetch (10s interval for summary, signals, open positions, current orders, statuses)
  const isFetchingSlow = useRef(false);
  const fetchSlowData = useCallback(async () => {
    if (isFetchingSlow.current) return;
    isFetchingSlow.current = true;
    try {
      const [sum, sig, posOpen, ordCurr, telSt, telMsg, brk, rsk, rskCfg, trdSt] = await Promise.allSettled([
        api.getDashboardSummary(),
        api.getSignals(),
        api.getPositions('open'),
        api.getOrders('current_session'),
        api.getTelegramStatus(),
        api.getTelegramMessages(),
        api.getBrokerStatus(),
        api.getRiskStatus(),
        api.getRiskConfig(),
        api.getTradingStatus(),
      ]);

      if (sum.status === 'fulfilled') setSummary(sum.value);
      if (sig.status === 'fulfilled') setSignals(sig.value);
      if (posOpen.status === 'fulfilled') setPositions(posOpen.value);
      if (ordCurr.status === 'fulfilled') setOrders(ordCurr.value);
      if (telSt.status === 'fulfilled') setTelegramStatus(telSt.value);
      if (telMsg.status === 'fulfilled') setTelegramMessages(telMsg.value);
      if (brk.status === 'fulfilled') setBrokerStatus(brk.value);
      if (rsk.status === 'fulfilled') setRiskStatus(rsk.value);
      if (rskCfg.status === 'fulfilled' && rskCfg.value) {
        setRiskConfig(rskCfg.value);
      }
      if (trdSt.status === 'fulfilled') setTradingStatus(trdSt.value);
    } catch (err: any) {
      console.error('Slow polling error:', err);
    } finally {
      isFetchingSlow.current = false;
    }
  }, []);

  // Historical / On-Demand Data Fetch
  const isFetchingHistorical = useRef(false);
  const fetchHistoricalData = useCallback(async () => {
    if (isFetchingHistorical.current) return;
    isFetchingHistorical.current = true;
    try {
      const [trdHist, posHist, ordHist, telCh, aud] = await Promise.allSettled([
        api.getTrades('history'),
        api.getPositions('history'),
        api.getOrders('history'),
        api.getTelegramChannels(),
        api.getAuditLogs(),
      ]);

      if (trdHist.status === 'fulfilled') setHistoryTrades(trdHist.value);
      if (posHist.status === 'fulfilled') setHistoryPositions(posHist.value);
      if (ordHist.status === 'fulfilled') setHistoryOrders(ordHist.value);
      if (telCh.status === 'fulfilled') setTelegramChannels(telCh.value);
      if (aud.status === 'fulfilled') setAuditLogs(aud.value);
    } catch (err: any) {
      console.error('Historical fetch error:', err);
    } finally {
      isFetchingHistorical.current = false;
    }
  }, []);

  // Central refresh helper (invoked on manual actions: simulation, injection, reset, etc.)
  const fetchAllData = useCallback(async () => {
    await Promise.allSettled([
      fetchRealtimeData(),
      fetchSlowData(),
      fetchHistoricalData(),
    ]);
  }, [fetchRealtimeData, fetchSlowData, fetchHistoricalData]);

  // Realtime Polling Loop (400ms)
  useEffect(() => {
    if (!authenticated) return;
    fetchRealtimeData();
    const interval = setInterval(fetchRealtimeData, 400);
    return () => clearInterval(interval);
  }, [fetchRealtimeData, authenticated]);

  // Slow Polling Loop (10s)
  useEffect(() => {
    if (!authenticated) return;
    fetchSlowData();
    const interval = setInterval(fetchSlowData, 10000);
    return () => clearInterval(interval);
  }, [fetchSlowData, authenticated]);

  // Initial mount load for historical data
  useEffect(() => {
    if (!authenticated) return;
    fetchHistoricalData();
  }, [fetchHistoricalData, authenticated]);

  // On-demand fetch when sub-tabs switch to history
  useEffect(() => {
    if (tradesView === 'history') {
      api.getTrades('history').then(setHistoryTrades).catch(console.error);
    }
  }, [tradesView]);

  useEffect(() => {
    if (positionsView === 'history') {
      api.getPositions('history').then(setHistoryPositions).catch(console.error);
    }
  }, [positionsView]);

  useEffect(() => {
    if (ordersView === 'history') {
      api.getOrders('history').then(setHistoryOrders).catch(console.error);
    }
  }, [ordersView]);

  // On-demand fetch when switching to tabs that need fresh data
  useEffect(() => {
    if (activeTab === 'audit_logs') {
      api.getAuditLogs().then(setAuditLogs).catch(console.error);
    } else if (activeTab === 'telegram') {
      api.getTelegramChannels().then(setTelegramChannels).catch(console.error);
    } else if (activeTab === 'risk') {
      api.getRiskConfig().then(setRiskConfig).catch(console.error);
      api.getRiskStatus().then(setRiskStatus).catch(console.error);
    }
  }, [activeTab]);

  // Sync form inputs when riskConfig is loaded or updated
  useEffect(() => {
    if (riskConfig) {
      setFormDailyLoss(riskConfig.max_daily_loss.toString());
      setFormRiskPerTrade(riskConfig.max_risk_per_trade.toString());
      setFormMaxTrades(riskConfig.max_trades_per_day.toString());
      setFormMaxPositions(riskConfig.max_simultaneous_positions.toString());
      setFormQuantityMode(riskConfig.quantity_mode || 'FIXED');
      setFormFixedLots(riskConfig.fixed_lots?.toString() || '1');
      setFormEntryTimeout(riskConfig.entry_timeout_minutes?.toString() || '15');
      setFormEntryTolerance(riskConfig.entry_tolerance?.toString() || '1.0');
      setFormDailyLossEnabled(riskConfig.daily_loss_protection_enabled);
      setFormMaxTradesEnabled(riskConfig.max_trades_protection_enabled);
      setFormMaxPositionsEnabled(riskConfig.max_positions_protection_enabled);
      setFormPartialProfitEnabled(riskConfig.partial_profit_enabled ?? false);
      setFormPartialProfitTrigger(riskConfig.partial_profit_trigger?.toString() || '10.0');
      setFormPartialProfitPercentage(riskConfig.partial_profit_percentage?.toString() || '50');
      setFormTrailingStopEnabled(riskConfig.trailing_stop_enabled ?? false);
      setFormTrailingMode(riskConfig.trailing_activation_mode || 'AFTER_PARTIAL_PROFIT');
      setFormTrailingActivationProfit(riskConfig.trailing_activation_profit?.toString() || '10.0');
      setFormTrailingDistance(riskConfig.trailing_distance?.toString() || '5.0');
    }
  }, [riskConfig?.updated_at]);

  // Handle Save Risk Configuration
  const handleSaveRiskConfig = async (e: React.FormEvent) => {
    e.preventDefault();
    setRiskSaving(true);
    setRiskMsg(null);

    const formData = new FormData(e.currentTarget as HTMLFormElement);
    
    const dailyLoss = parseFloat(formData.get('max_daily_loss') as string);
    const riskPerTrade = parseFloat(formData.get('max_risk_per_trade') as string) || riskConfig?.max_risk_per_trade || 1000;
    const maxTrades = parseInt(formData.get('max_trades_per_day') as string, 10);
    const maxPositions = parseInt(formData.get('max_simultaneous_positions') as string, 10);
    const quantityMode = (formData.get('quantity_mode') as string) || 'FIXED';
    const fixedLots = parseInt(formData.get('fixed_lots') as string, 10) || riskConfig?.fixed_lots || 1;
    const entryTimeout = parseInt(formData.get('entry_timeout_minutes') as string, 10);
    const entryTolerance = parseFloat(formData.get('entry_tolerance') as string);
    const partialProfitTrigger = parseFloat(formData.get('partial_profit_trigger') as string) || riskConfig?.partial_profit_trigger || 10.0;
    const partialProfitPercentage = parseFloat(formData.get('partial_profit_percentage') as string) || riskConfig?.partial_profit_percentage || 50.0;
    
    const trailingMode = formData.get('trailing_activation_mode') as string || riskConfig?.trailing_activation_mode || 'AFTER_PARTIAL_PROFIT';
    // Use fallback for trailingActivationProfit if it evaluates to NaN, but still conditionally extract it.
    let tap = parseFloat(formData.get('trailing_activation_profit') as string);
    const trailingActivationProfit = !isNaN(tap) ? tap : (riskConfig?.trailing_activation_profit || 10.0);
    const trailingDistance = parseFloat(formData.get('trailing_distance') as string) || riskConfig?.trailing_distance || 5.0;

    // Switches return 'on' when checked
    const dailyLossEnabled = formData.get('daily_loss_protection_enabled') === 'on';
    const maxTradesEnabled = formData.get('max_trades_protection_enabled') === 'on';
    const maxPositionsEnabled = formData.get('max_positions_protection_enabled') === 'on';
    const partialProfitEnabled = formData.get('partial_profit_enabled') === 'on';
    const trailingStopEnabled = formData.get('trailing_stop_enabled') === 'on';

    if (isNaN(dailyLoss) || dailyLoss <= 0) {
      setRiskMsg({ type: 'error', text: 'Max Daily Loss must be a positive number greater than 0.' });
      setRiskSaving(false);
      return;
    }
    if (quantityMode === 'RISK_BASED' && (isNaN(riskPerTrade) || riskPerTrade <= 0)) {
      setRiskMsg({ type: 'error', text: 'Max Risk Per Trade must be a positive number greater than 0.' });
      setRiskSaving(false);
      return;
    }
    if (isNaN(maxTrades) || maxTrades <= 0) {
      setRiskMsg({ type: 'error', text: 'Max Trades Per Day must be an integer greater than 0.' });
      setRiskSaving(false);
      return;
    }
    if (isNaN(maxPositions) || maxPositions <= 0) {
      setRiskMsg({ type: 'error', text: 'Max Simultaneous Positions must be an integer greater than 0.' });
      setRiskSaving(false);
      return;
    }
    if (quantityMode === 'FIXED' && (isNaN(fixedLots) || fixedLots <= 0)) {
      setRiskMsg({ type: 'error', text: 'Fixed Lots must be an integer greater than 0.' });
      setRiskSaving(false);
      return;
    }
    if (isNaN(entryTimeout) || entryTimeout < 1 || entryTimeout > 60) {
      setRiskMsg({ type: 'error', text: 'Entry Timeout must be an integer between 1 and 60 minutes.' });
      setRiskSaving(false);
      return;
    }
    if (isNaN(entryTolerance) || entryTolerance < 0 || entryTolerance > 100) {
      setRiskMsg({ type: 'error', text: 'Entry Tolerance must be a number between 0 and 100.' });
      setRiskSaving(false);
      return;
    }

    try {
      const updated = await api.updateRiskConfig({
        max_daily_loss: dailyLoss,
        max_risk_per_trade: riskPerTrade,
        max_trades_per_day: maxTrades,
        max_simultaneous_positions: maxPositions,
        quantity_mode: quantityMode,
        fixed_lots: fixedLots,
        daily_loss_protection_enabled: dailyLossEnabled,
        max_trades_protection_enabled: maxTradesEnabled,
        max_positions_protection_enabled: maxPositionsEnabled,
        is_algo_active: riskConfig?.is_algo_active ?? true,
        entry_timeout_minutes: entryTimeout,
        entry_tolerance: entryTolerance,
        partial_profit_enabled: partialProfitEnabled,
        partial_profit_trigger: partialProfitTrigger,
        partial_profit_percentage: partialProfitPercentage,
        trailing_stop_enabled: trailingStopEnabled,
        trailing_activation_mode: trailingMode,
        trailing_activation_profit: trailingActivationProfit,
        trailing_distance: trailingDistance
      });
      setRiskConfig(updated.config);
      setRiskMsg({ type: 'success', text: 'Risk configuration updated successfully and active immediately.' });
      fetchAllData();
    } catch (err: any) {
      setRiskMsg({ type: 'error', text: err.message || 'Failed to update risk configuration.' });
    } finally {
      setRiskSaving(false);
    }
  };

  // Open Trade Detail Modal
  const openTradeDetail = async (tradeId: number) => {
    setDetailLoading(true);
    try {
      const detail = await api.getTradeDetail(tradeId);
      setSelectedTradeDetail(detail);
    } catch (err) {
      console.error('Failed to load trade detail:', err);
    } finally {
      setDetailLoading(false);
    }
  };

  // Handle Paper Signal Simulation
  const handleSimulateSignal = async (e: React.FormEvent) => {
    e.preventDefault();
    setSimSubmitting(true);
    setSimStatus(null);
    try {
      const res = await api.simulateSignal({
        underlying: simUnderlying,
        strike: parseInt(simStrike, 10),
        option_type: simOptionType,
        expiry: simExpiry,
        entry_trigger: parseFloat(simEntry),
        stop_loss: parseFloat(simSL),
        target: parseFloat(simTarget)
      });
      setSimStatus(res);
      if (res.instrument_token) {
        setInjectToken(res.instrument_token);
      }
      fetchAllData();
    } catch (err: any) {
      setSimStatus({ status: 'ERROR', message: err.message });
    } finally {
      setSimSubmitting(false);
    }
  };

  // Handle Inject Price
  const handleInjectPrice = async (e: React.FormEvent) => {
    e.preventDefault();
    setInjectSubmitting(true);
    setInjectStatus(null);
    try {
      const res = await api.injectPrice(injectToken, parseFloat(injectPrice));
      setInjectStatus(res);
      fetchAllData();
    } catch (err: any) {
      setInjectStatus({ status: 'ERROR', message: err.message });
    } finally {
      setInjectSubmitting(false);
    }
  };

  // Handle Paper State Reset
  const handleResetPaperState = async () => {
    setResettingPaper(true);
    setResetAlert(null);
    try {
      const res = await api.resetPaperState();
      setResetAlert({
        type: 'success',
        message: `Paper reset complete: ${res.positions_reset} positions reset, ${res.paper_trades_reset_closed} trades closed. Live broker untouched.`
      });
      setShowResetModal(false);
      fetchAllData();
    } catch (err: any) {
      setResetAlert({
        type: 'error',
        message: err.message || 'Failed to reset paper state'
      });
    } finally {
      setResettingPaper(false);
    }
  };

  // Telegram User Client Handlers
  const handleSendCode = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!authPhone.trim()) return;
    setTelegramAuthLoading(true);
    setAuthMsg(null);
    try {
      await api.sendTelegramCode(authPhone.trim());
      setAuthStep('code');
      setAuthMsg({ type: 'success', text: `Login code sent to ${authPhone}` });
    } catch (err: any) {
      setAuthMsg({ type: 'error', text: err.message || 'Failed to send code' });
    } finally {
      setTelegramAuthLoading(false);
    }
  };

  const handleSignIn = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!authCode.trim()) return;
    setTelegramAuthLoading(true);
    setAuthMsg(null);
    try {
      const res = await api.signInTelegram(authPhone.trim(), authCode.trim(), authPassword.trim() || undefined);
      if (res.status === '2FA_REQUIRED') {
        setAuthMsg({ type: 'error', text: 'Two-factor authentication required. Please enter your 2FA password.' });
      } else {
        setAuthMsg({ type: 'success', text: 'Authenticated successfully!' });
        setAuthStep('phone');
        setAuthCode('');
        setAuthPassword('');
        fetchAllData();
      }
    } catch (err: any) {
      setAuthMsg({ type: 'error', text: err.message || 'Failed to sign in' });
    } finally {
      setTelegramAuthLoading(false);
    }
  };

  const handleLogout = async () => {
    setTelegramAuthLoading(true);
    setAuthMsg(null);
    try {
      await api.logoutTelegram();
      setAuthMsg({ type: 'success', text: 'Logged out successfully.' });
      fetchAllData();
    } catch (err: any) {
      setAuthMsg({ type: 'error', text: err.message });
    } finally {
      setTelegramAuthLoading(false);
    }
  };

  const handleSelectChannel = async (channelId: string, channelName: string) => {
    setSelectingChannelId(channelId);
    try {
      await api.selectTelegramChannel(channelId, channelName);
      fetchAllData();
    } catch (err: any) {
      console.error('Failed to select channel:', err);
    } finally {
      setSelectingChannelId(null);
    }
  };

  const fetchChannels = async () => {
    try {
      const chs = await api.getTelegramChannels();
      setTelegramChannels(chs);
    } catch (err) {
      console.error('Failed to fetch channels:', err);
    }
  };

  const handleOpenChannelSelector = () => {
    fetchChannels();
    setShowChannelSelector(true);
  };

  // Remove the old auth checks from App.tsx since ProtectedRoute handles it


  return (
    <>
      <Routes>
        <Route path="/login" element={<LoginPage />} />
        <Route element={<ProtectedRoute />}>
          <Route element={
            <AppShell
              tradingMode={summary?.mode || 'PAPER'}
              sfeedStatus={summary?.connections?.sfeed?.status || 'DISCONNECTED'}
              telegramStatus={summary?.connections?.telegram?.status || 'DISCONNECTED'}
              newTradesPaused={summary?.metrics?.new_trades_paused || false}
            >
              <Outlet />
            </AppShell>
          }>
          <Route path="/" element={<Navigate to="/dashboard" replace />} />
          <Route path="dashboard" element={
            <DashboardOverview
              summary={summary}
              activeTrades={trades.filter(t => ['WAITING_FOR_ENTRY', 'ENTRY_TRIGGERED', 'POSITION_OPEN', 'PARTIAL_PROFIT', 'Trailing Stop'].includes(t.status) || ['TRAILING_STOP'].includes(t.status))}
              positions={positions}
              riskConfig={riskConfig}
              onTradeClick={(t) => openTradeDetail(t.id)}
            />
          } />
          <Route path="market" element={<MarketDataCard summary={summary} subscriptions={marketSubs} />} />
          <Route path="controls" element={<OperationalControls summary={summary} refreshData={fetchSlowData} />} />
          <Route path="system" element={<SystemHealthPage summary={summary} />} />
          <Route path="audit" element={<AuditLogsPage />} />
          <Route path="signals" element={<SignalsTab signals={signals} />} />
          <Route path="trades" element={
            <TradesTab 
              activeTrades={trades} 
              historyTrades={historyTrades} 
              view={tradesView} 
              onViewChange={setTradesView} 
              onTradeClick={(t) => openTradeDetail(t.id)} 
            />
          } />
          <Route path="positions" element={
            <PositionsTab 
              positions={positions} 
              historyPositions={historyPositions} 
              view={positionsView} 
              onViewChange={setPositionsView} 
            />
          } />
          <Route path="orders" element={
            <OrdersTab 
              orders={orders} 
              historyOrders={historyOrders} 
              view={ordersView} 
              onViewChange={setOrdersView} 
            />
          } />
          <Route path="risk" element={
            <RiskManagementTab 
              riskConfig={riskConfig} 
              onSaveRiskConfig={handleSaveRiskConfig} 
              saving={riskSaving} 
              message={riskMsg} 
            />
          } />
          <Route path="telegram" element={
            <TelegramPage
              status={telegramStatus}
              messages={telegramMessages}
              onRefreshData={fetchSlowData}
              onOpenChannelSelector={handleOpenChannelSelector}
            />
          } />
          <Route path="connections" element={
            <BrokerPage status={brokerStatus} />
          } />
          <Route path="journal" element={<Journal initialTab={0} />} />
          <Route path="analytics" element={<Journal initialTab={1} />} />
          
          {/* Catch-all for protected routes (Under Construction logic) */}
          <Route path="*" element={
            <div style={{ padding: 48, display: 'flex', alignItems: 'center', justifyContent: 'center', border: '2px dashed #e2e8f0', borderRadius: 12, margin: 16, backgroundColor: '#f8fafc' }}>
              <div style={{ textAlign: 'center' }}>
                <h3 style={{ fontWeight: 600, color: '#1e293b', fontSize: '1.125rem' }}>Under Construction</h3>
                <p style={{ color: '#64748b', maxWidth: 320 }}>This section is currently being migrated to the new professional terminal UI. Please check back later.</p>
              </div>
            </div>
          } />
          </Route>
        </Route>
      </Routes>

      {selectedTradeDetail && (
        <TradeDetailDrawer
          detail={selectedTradeDetail}
          loading={detailLoading}
          onClose={() => setSelectedTradeDetail(null)}
        />
      )}

      {showChannelSelector && (
        <ChannelSelectorDialog
          open={showChannelSelector}
          onClose={() => setShowChannelSelector(false)}
          channels={telegramChannels}
          selectedChannelId={telegramStatus?.selected_channel?.channel_id || null}
          onSelectChannel={(id, name) => {
            setShowChannelSelector(false);
            handleSelectChannel(id, name);
          }}
          loading={selectingChannelId !== null}
          onRefreshChannels={fetchChannels}
        />
      )}
    </>
  );
}
