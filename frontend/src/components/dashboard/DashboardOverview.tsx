import type { DashboardSummary, TradeItem, PositionItem, RiskConfig, MarketOverviewData } from '@/types';
import { KpiCard } from "./KpiCard";
import { ActiveTradesTable } from "./ActiveTradesTable";
import { TradingSessionSnapshot } from "./TradingSessionSnapshot";
import TrendingUpIcon from "@mui/icons-material/TrendingUp";
import ActivityIcon from "@mui/icons-material/ShowChart";
import BriefcaseIcon from "@mui/icons-material/BusinessCenter";
import ListOrderedIcon from "@mui/icons-material/FormatListNumbered";
import PercentIcon from "@mui/icons-material/Percent";
import PieChartIcon from "@mui/icons-material/PieChart";
import ShieldCheckIcon from "@mui/icons-material/VerifiedUser";
import Grid from "@mui/material/Grid";
import Box from "@mui/material/Box";
import Typography from "@mui/material/Typography";
import Card from "@mui/material/Card";
import CardContent from "@mui/material/CardContent";
import CardHeader from "@mui/material/CardHeader";
interface DashboardOverviewProps {
  summary: DashboardSummary | null;
  activeTrades: TradeItem[];
  positions: PositionItem[];
  riskConfig: RiskConfig | null;
  marketOverview: MarketOverviewData | null;
  onTradeClick: (trade: TradeItem) => void;
}

export function DashboardOverview({
  summary,
  activeTrades,
  positions,
  riskConfig,
  marketOverview,
  onTradeClick
}: DashboardOverviewProps) {
  
  const todayPnl = summary?.metrics.today_pnl ?? 0;
  const winRate = summary?.metrics.win_rate ?? 0;
  const liveOptionPnl = positions.reduce((acc, pos) => acc + (pos.unrealized_pnl || 0), 0);
  
  return (
    <Box sx={{ animation: 'fadeIn 0.3s' }}>
      
      {summary?.mode === 'LIVE' && summary?.live_trading_enabled ? (
        <Box sx={{ mb: 1.5, p: 1.5, bgcolor: 'error.main', color: 'error.contrastText', borderRadius: 1, display: 'flex', alignItems: 'center' }}>
          <ShieldCheckIcon sx={{ mr: 1 }} />
          <Typography variant="subtitle1" sx={{ fontWeight: 'bold' }}>
            LIVE TRADING ENABLED - REAL ORDERS WILL BE PLACED
          </Typography>
        </Box>
      ) : (
        <Box sx={{ mb: 1.5, p: 0.75, px: 1.5, bgcolor: 'info.main', color: 'info.contrastText', borderRadius: 1, display: 'inline-flex', alignItems: 'center' }}>
          <ShieldCheckIcon sx={{ mr: 1 }} fontSize="small" />
          <Typography variant="body2" sx={{ fontWeight: 'bold' }}>
            PAPER TRADING - SAFE MODE
          </Typography>
        </Box>
      )}

      <Grid container spacing={1.5} sx={{ mb: 1.5 }}>
        <Grid size={{ xs: 6, md: 4, lg: 2 }}>
          <KpiCard
            title="Today's P&L"
            value={`₹${todayPnl.toFixed(2)}`}
            subtitle="Realized Profit"
            icon={<TrendingUpIcon fontSize="small" />}
            statusText={todayPnl >= 0 ? "PROFIT" : "LOSS"}
            statusColor={todayPnl >= 0 ? "success" : "error"}
            valueColor={todayPnl >= 0 ? "success.main" : "error.main"}
          />
        </Grid>
        
        <Grid size={{ xs: 6, md: 4, lg: 2 }}>
          <KpiCard
            title="Active Trades"
            value={activeTrades.length}
            subtitle={`${activeTrades.filter(t => t.status === 'WAITING_FOR_ENTRY').length} waiting · ${activeTrades.filter(t => ['ENTRY_TRIGGERED', 'POSITION_OPEN', 'PARTIAL_PROFIT'].includes(t.status)).length} open`}
            icon={<ActivityIcon fontSize="small" />}
          />
        </Grid>

        <Grid size={{ xs: 6, md: 4, lg: 2 }}>
          <KpiCard
            title="Open Position P&L"
            value={`₹${liveOptionPnl.toFixed(2)}`}
            subtitle="Live Unrealized"
            icon={<BriefcaseIcon fontSize="small" />}
            valueColor={liveOptionPnl > 0 ? 'success.main' : liveOptionPnl < 0 ? 'error.main' : 'text.primary'}
          />
        </Grid>

        <Grid size={{ xs: 6, md: 4, lg: 2 }}>
          <KpiCard
            title="Trades Today"
            value={summary?.metrics.orders_today ?? 0}
            subtitle="Executed Fills"
            icon={<ListOrderedIcon fontSize="small" />}
          />
        </Grid>

        <Grid size={{ xs: 6, md: 4, lg: 2 }}>
          <KpiCard
            title="Win Rate"
            value={`${winRate.toFixed(1)}%`}
            subtitle="Last 30 Days"
            icon={<PercentIcon fontSize="small" />}
            statusText={winRate >= 50 ? "GOOD" : "NEEDS WORK"}
            statusColor={winRate >= 50 ? "success" : "warning"}
          />
        </Grid>

        <Grid size={{ xs: 6, md: 4, lg: 2 }}>
          <KpiCard
            title="P/L Trades"
            value={
              <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                <Typography variant="h4" sx={{ fontWeight: 700, color: 'success.main' }}>
                  {summary?.metrics.winning_trades ?? 0}
                </Typography>
                <Typography variant="h4" sx={{ fontWeight: 700, color: 'text.disabled' }}>
                  /
                </Typography>
                <Typography variant="h4" sx={{ fontWeight: 700, color: 'error.main' }}>
                  {summary?.metrics.losing_trades ?? 0}
                </Typography>
              </Box>
            }
            subtitle="Profitable / Losing"
            icon={<PieChartIcon fontSize="small" />}
          />
        </Grid>
      </Grid>



      <Grid container spacing={2}>
        <Grid size={{ xs: 12, lg: 8 }}>
          <Box sx={{ display: 'flex', alignItems: 'center', mb: 1 }}>
            <ActivityIcon fontSize="small" sx={{ mr: 1, color: 'text.secondary' }} />
            <Typography variant="subtitle2" sx={{ fontWeight: 'bold' }}>Active Trades</Typography>
          </Box>
          <ActiveTradesTable 
            trades={activeTrades} 
            positions={positions} 
            onTradeClick={onTradeClick} 
          />
        </Grid>
        
        <Grid size={{ xs: 12, lg: 4 }}>
          <Box sx={{ mb: 1.5 }}>
            <TradingSessionSnapshot summary={summary} riskConfig={riskConfig} positions={positions} />
          </Box>
          <Card elevation={2}>
            <CardHeader 
              title="System Health" 
              titleTypographyProps={{ variant: 'subtitle2', fontWeight: 'bold' }}
              sx={{ borderBottom: 1, borderColor: 'divider', pb: 1.5, pt: 2 }}
            />
            <CardContent>
              <Box sx={{ display: 'flex', justifyContent: 'space-between', mb: 1 }}>
                <Typography variant="body2" color="text.secondary">Kotak API</Typography>
                <Typography variant="body2" sx={{ fontWeight: 'bold' }} color={marketOverview?.system_health?.kotak_api === 'CONNECTED' ? 'success.main' : 'error.main'}>
                  {marketOverview?.system_health?.kotak_api || 'UNKNOWN'}
                </Typography>
              </Box>
              <Box sx={{ display: 'flex', justifyContent: 'space-between', mb: 1 }}>
                <Typography variant="body2" color="text.secondary">Market Data Feed</Typography>
                <Typography variant="body2" sx={{ fontWeight: 'bold' }} color={marketOverview?.system_health?.market_data_feed === 'CONNECTED' ? 'success.main' : 'error.main'}>
                  {marketOverview?.system_health?.market_data_feed || 'UNKNOWN'}
                </Typography>
              </Box>
              <Box sx={{ display: 'flex', justifyContent: 'space-between', mb: 1 }}>
                <Typography variant="body2" color="text.secondary">Telegram Listener</Typography>
                <Typography variant="body2" sx={{ fontWeight: 'bold' }} color={marketOverview?.system_health?.telegram_listener === 'LISTENING' ? 'success.main' : 'warning.main'}>
                  {marketOverview?.system_health?.telegram_listener || 'UNKNOWN'}
                </Typography>
              </Box>
              <Box sx={{ display: 'flex', justifyContent: 'space-between' }}>
                <Typography variant="body2" color="text.secondary">Database</Typography>
                <Typography variant="body2" sx={{ fontWeight: 'bold' }} color={marketOverview?.system_health?.database === 'CONNECTED' ? 'success.main' : 'error.main'}>
                  {marketOverview?.system_health?.database || 'UNKNOWN'}
                </Typography>
              </Box>
            </CardContent>
          </Card>
        </Grid>
      </Grid>
      
    </Box>
  );
}
