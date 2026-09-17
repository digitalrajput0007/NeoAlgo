import type { DashboardSummary, MarketSubscription } from '@/types';
import Card from "@mui/material/Card";
import CardContent from "@mui/material/CardContent";
import CardHeader from "@mui/material/CardHeader";
import Table from "@mui/material/Table";
import TableBody from "@mui/material/TableBody";
import TableCell from "@mui/material/TableCell";
import TableContainer from "@mui/material/TableContainer";
import TableHead from "@mui/material/TableHead";
import TableRow from "@mui/material/TableRow";
import Paper from "@mui/material/Paper";
import Typography from "@mui/material/Typography";
import Box from "@mui/material/Box";
import Grid from "@mui/material/Grid";
import { StatusBadge } from "@/components/shared/StatusBadge";
import { EmptyState } from "@/components/shared/EmptyState";
import TimelineIcon from "@mui/icons-material/Timeline";
import WifiIcon from "@mui/icons-material/Wifi";

interface MarketDataCardProps {
  summary: DashboardSummary | null;
  subscriptions: MarketSubscription[];
}

export function MarketDataCard({ summary, subscriptions }: MarketDataCardProps) {
  const sfeed = summary?.connections?.sfeed;

  return (
    <Box sx={{ animation: 'fadeIn 0.3s' }}>
      <Card elevation={2}>
        <CardHeader
          avatar={<TimelineIcon color="primary" />}
          title="Market Data"
          action={<StatusBadge status={sfeed?.status || 'DISCONNECTED'} />}
          sx={{ borderBottom: 1, borderColor: 'divider' }}
        />
        <CardContent sx={{ pt: 3 }}>
          <Grid container spacing={3} sx={{ mb: 4 }}>
            <Grid size={{ xs: 6, md: 3 }}>
              <Typography variant="overline" color="text.secondary" sx={{ fontWeight: 700 }}>Subscriptions</Typography>
              <Typography variant="h5" sx={{ fontWeight: 700 }}>{sfeed?.active_subscriptions ?? 0}</Typography>
            </Grid>
            <Grid size={{ xs: 6, md: 3 }}>
              <Typography variant="overline" color="text.secondary" sx={{ fontWeight: 700 }}>Total Ticks</Typography>
              <Typography variant="h5" sx={{ fontWeight: 700 }}>{sfeed?.total_ticks ?? 0}</Typography>
            </Grid>
            <Grid size={{ xs: 6, md: 3 }}>
              <Typography variant="overline" color="text.secondary" sx={{ fontWeight: 700 }}>Last Update</Typography>
              <Typography variant="body1" sx={{ fontFamily: 'monospace', mt: 0.5 }}>
                {sfeed?.last_tick_time ? new Date(sfeed.last_tick_time).toLocaleTimeString() : 'Never'}
              </Typography>
            </Grid>
          </Grid>

          <Box sx={{ borderTop: 1, borderColor: 'divider', pt: 3 }}>
            <Box sx={{ display: 'flex', alignItems: 'center', mb: 2 }}>
              <WifiIcon fontSize="small" sx={{ mr: 1, color: 'text.secondary' }} />
              <Typography variant="subtitle2" sx={{ fontWeight: 'bold' }}>Active Subscriptions</Typography>
            </Box>
            
            {subscriptions.length === 0 ? (
              <EmptyState 
                title="No Active Subscriptions" 
                description="The system is not currently subscribed to any instrument data feeds." 
              />
            ) : (
              <TableContainer component={Paper} elevation={0} variant="outlined">
                <Table size="small">
                  <TableHead sx={{ bgcolor: 'grey.50' }}>
                    <TableRow>
                      <TableCell>Instrument</TableCell>
                      <TableCell>Token</TableCell>
                      <TableCell align="right" sx={{ fontWeight: 700, color: 'warning.dark' }}>LTP</TableCell>
                      <TableCell align="right">Last Tick</TableCell>
                    </TableRow>
                  </TableHead>
                  <TableBody>
                    {subscriptions.map(sub => (
                      <TableRow key={sub.instrument_token} hover sx={{ '&:last-child td, &:last-child th': { border: 0 } }}>
                        <TableCell sx={{ fontWeight: 700 }}>
                          {sub.pSymbol 
                            ? `${sub.pSymbol} ${sub.strike ? (sub.strike % 1 === 0 ? sub.strike : sub.strike.toString()) : ''} ${sub.option_type || ''}`.trim() 
                            : (sub.pTrdSymbol || '—')}
                        </TableCell>
                        <TableCell sx={{ fontFamily: 'monospace', color: 'text.secondary' }}>{sub.instrument_token}</TableCell>
                        <TableCell align="right" sx={{ fontFamily: 'monospace', fontWeight: 700, bgcolor: 'warning.50' }}>
                          {(sub.latest_ltp ?? 0) > 0 ? `₹${(sub.latest_ltp ?? 0).toFixed(2)}` : '—'}
                        </TableCell>
                        <TableCell align="right" sx={{ fontFamily: 'monospace', fontSize: '0.75rem', color: 'text.disabled' }}>
                          {sub.last_tick ? new Date(sub.last_tick).toLocaleTimeString() : '—'}
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </TableContainer>
            )}
          </Box>
        </CardContent>
      </Card>
    </Box>
  );
}
