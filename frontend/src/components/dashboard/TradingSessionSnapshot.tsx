import type { DashboardSummary, RiskConfig } from '@/types';
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
}

export function TradingSessionSnapshot({ summary, riskConfig }: TradingSessionSnapshotProps) {
  if (!summary || !riskConfig) return null;

  const realizedPnl = summary.metrics.today_pnl ?? 0;
  const maxLoss = riskConfig.max_daily_loss;
  const lossProgress = realizedPnl < 0 ? Math.min((Math.abs(realizedPnl) / maxLoss) * 100, 100) : 0;
  
  const tradesToday = summary.metrics.orders_today ?? 0;
  const maxTrades = riskConfig.max_trades_per_day;
  const tradesProgress = Math.min((tradesToday / maxTrades) * 100, 100);

  return (
    <Card elevation={2} sx={{ height: '100%' }}>
      <CardHeader 
        title={
          <Box sx={{ display: 'flex', alignItems: 'center' }}>
            <WalletIcon sx={{ mr: 1, color: 'text.secondary' }} fontSize="small" />
            Trading Session
          </Box>
        }
        titleTypographyProps={{ variant: 'subtitle2', fontWeight: 'bold' }}
        sx={{ borderBottom: 1, borderColor: 'divider', pb: 1.5, pt: 2 }}
      />
      <CardContent sx={{ pt: 2 }}>
        
        <Box sx={{ mb: 3 }}>
          <Typography variant="body2" color="text.secondary" sx={{ mb: 0.5, fontWeight: 600 }}>Today's Realized P&L</Typography>
          <Typography variant="h5" color={realizedPnl >= 0 ? "success.main" : "error.main"} sx={{ mb: 1, fontFamily: '"Poppins", sans-serif', fontWeight: 800 }}>
            ₹{realizedPnl.toFixed(2)}
          </Typography>
          {riskConfig.daily_loss_protection_enabled && (
            <>
              <LinearProgress variant="determinate" value={lossProgress} color={realizedPnl >= 0 ? "success" : "error"} sx={{ height: 6, borderRadius: 3, mb: 0.5 }} />
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

        <Box sx={{ pt: 1.5, borderTop: 1, borderColor: 'divider' }}>
          <Typography variant="body2" color="text.secondary" sx={{ mb: 0.5, fontWeight: 600 }}>Risk Per Trade Limit</Typography>
          <Typography variant="h6" sx={{ fontFamily: '"Poppins", monospace', bgcolor: 'grey.100', display: 'inline-block', px: 1.5, py: 0.5, borderRadius: 2, fontWeight: 700 }}>
            ₹{riskConfig.max_risk_per_trade}
          </Typography>
        </Box>
      </CardContent>
    </Card>
  );
}
