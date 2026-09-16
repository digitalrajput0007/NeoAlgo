import type { DashboardSummary, TradeItem, PositionItem, RiskConfig } from '@/types';
import { KpiCard } from "./KpiCard";
import { ActiveTradesTable } from "./ActiveTradesTable";
import { TradingSessionSnapshot } from "./TradingSessionSnapshot";
import TrendingUpIcon from "@mui/icons-material/TrendingUp";
import ActivityIcon from "@mui/icons-material/ShowChart";
import BriefcaseIcon from "@mui/icons-material/BusinessCenter";
import ListOrderedIcon from "@mui/icons-material/FormatListNumbered";
import PercentIcon from "@mui/icons-material/Percent";
import ShieldCheckIcon from "@mui/icons-material/VerifiedUser";
import Grid from "@mui/material/Grid";
import Box from "@mui/material/Box";
import Typography from "@mui/material/Typography";

interface DashboardOverviewProps {
  summary: DashboardSummary | null;
  activeTrades: TradeItem[];
  positions: PositionItem[];
  riskConfig: RiskConfig | null;
  onTradeClick: (trade: TradeItem) => void;
}

export function DashboardOverview({
  summary,
  activeTrades,
  positions,
  riskConfig,
  onTradeClick
}: DashboardOverviewProps) {
  
  const todayPnl = summary?.metrics.today_pnl ?? 0;
  const winRate = 0;
  
  return (
    <Box sx={{ animation: 'fadeIn 0.3s' }}>
      
      <Grid container spacing={2} sx={{ mb: 3 }}>
        <Grid size={{ xs: 6, md: 4, lg: 2 }}>
          <KpiCard
            title="Today's P&L"
            value={`₹${todayPnl.toFixed(2)}`}
            subtitle="Realized + Unrealized"
            icon={<TrendingUpIcon fontSize="small" />}
            statusText={todayPnl >= 0 ? "PROFIT" : "LOSS"}
            statusColor={todayPnl >= 0 ? "success" : "error"}
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
            title="Open Positions"
            value={positions.filter(p => p.quantity !== 0).length}
            subtitle="Held in Paper Account"
            icon={<BriefcaseIcon fontSize="small" />}
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
            title="Available Risk"
            value={`₹${riskConfig?.max_risk_per_trade ?? 0}`}
            subtitle="Configured Max Per Trade"
            icon={<ShieldCheckIcon fontSize="small" />}
          />
        </Grid>
      </Grid>

      <Grid container spacing={3}>
        <Grid size={{ xs: 12, lg: 8 }}>
          <Box sx={{ display: 'flex', alignItems: 'center', mb: 2 }}>
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
          <TradingSessionSnapshot summary={summary} riskConfig={riskConfig} />
        </Grid>
      </Grid>
      
    </Box>
  );
}
