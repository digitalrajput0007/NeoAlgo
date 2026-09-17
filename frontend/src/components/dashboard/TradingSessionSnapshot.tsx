import type { DashboardSummary, RiskConfig, PositionItem } from '@/types';
import Card from "@mui/material/Card";
import CardContent from "@mui/material/CardContent";
import CardHeader from "@mui/material/CardHeader";
import Typography from "@mui/material/Typography";
import LinearProgress from "@mui/material/LinearProgress";
import Box from "@mui/material/Box";
import WalletIcon from "@mui/icons-material/AccountBalanceWallet";

interface TradingSessionSnapshotProps {
  summary: DashboardSummary | null;
  riskConfig: RiskConfig | null;
  positions: PositionItem[];
}

export function TradingSessionSnapshot({ summary, riskConfig, positions }: TradingSessionSnapshotProps) {
  if (!summary || !riskConfig) return null;

  // Calculate live unrealized P&L for open option positions
  const openPositions = positions.filter(p => p.quantity > 0);
  const liveOptionPnl = openPositions.reduce((acc, pos) => acc + (pos.unrealized_pnl || 0), 0);

  const maxLoss = riskConfig.max_daily_loss;
  // If the user meant liveOptionPnl for loss progress, we use it; else fallback to realizedPnl if needed
  // We'll use the liveOptionPnl for the main display as requested.
  const lossProgress = liveOptionPnl < 0 ? Math.min((Math.abs(liveOptionPnl) / maxLoss) * 100, 100) : 0;
  
  const tradesToday = summary.metrics.orders_today ?? 0;
  const maxTrades = riskConfig.max_trades_per_day;
  const tradesProgress = Math.min((tradesToday / maxTrades) * 100, 100);

  return (
    <Card elevation={2} sx={{ height: '100%' }}>
      <CardHeader 
        title={
          <Box sx={{ display: 'flex', alignItems: 'center' }}>
            <WalletIcon sx={{ mr: 1, color: 'text.secondary' }} fontSize="small" />
            Open Position P&L
          </Box>
        }
        titleTypographyProps={{ variant: 'subtitle2', fontWeight: 'bold' }}
        sx={{ borderBottom: 1, borderColor: 'divider', pb: 1.5, pt: 2 }}
      />
      <CardContent sx={{ pt: 2 }}>
        
        <Box sx={{ mb: 3 }}>
          <Typography variant="body2" color="text.secondary" sx={{ mb: 0.5, fontWeight: 600 }}>Live Position P&L</Typography>
          <Typography variant="h5" color={liveOptionPnl >= 0 ? "success.main" : "error.main"} sx={{ mb: 1, fontFamily: '"Poppins", sans-serif', fontWeight: 800 }}>
            ₹{liveOptionPnl.toFixed(2)}
          </Typography>
          {riskConfig.daily_loss_protection_enabled && (
            <>
              <LinearProgress variant="determinate" value={lossProgress} color={liveOptionPnl >= 0 ? "success" : "error"} sx={{ height: 6, borderRadius: 3, mb: 0.5 }} />
              <Box sx={{ display: 'flex', justifyContent: 'space-between' }}>
                <Typography variant="caption" color="text.disabled">Loss Progress</Typography>
                <Typography variant="caption" color="text.disabled">Max: -₹{maxLoss}</Typography>
              </Box>
            </>
          )}
        </Box>

        <Box sx={{ mb: 3 }}>
          <Typography variant="body2" color="text.secondary" sx={{ mb: 0.5, fontWeight: 600 }}>Trades Executed</Typography>
          <Typography variant="h6" sx={{ mb: 1, fontWeight: 700 }}>{tradesToday} / {maxTrades}</Typography>
          {riskConfig.max_trades_protection_enabled && (
            <>
              <LinearProgress variant="determinate" value={tradesProgress} color="primary" sx={{ height: 6, borderRadius: 3, mb: 0.5 }} />
              <Box sx={{ display: 'flex', justifyContent: 'space-between' }}>
                <Typography variant="caption" color="text.disabled">Execution Progress</Typography>
                <Typography variant="caption" color="text.disabled">Max: {maxTrades} trades</Typography>
              </Box>
            </>
          )}
        </Box>
      </CardContent>
    </Card>
  );
}
