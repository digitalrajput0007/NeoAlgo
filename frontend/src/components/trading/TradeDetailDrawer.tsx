import React from 'react';
import type { TradeDetail } from '../../types';
import { formatLocalTime } from '../../utils/timezone';
import Drawer from "@mui/material/Drawer";
import IconButton from "@mui/material/IconButton";
import CloseIcon from "@mui/icons-material/Close";
import Typography from "@mui/material/Typography";
import Box from "@mui/material/Box";
import Grid from "@mui/material/Grid";
import Paper from "@mui/material/Paper";
import Chip from "@mui/material/Chip";
import CircularProgress from "@mui/material/CircularProgress";
import Stepper from "@mui/material/Stepper";
import Step from "@mui/material/Step";
import StepLabel from "@mui/material/StepLabel";
import StepContent from "@mui/material/StepContent";

interface TradeDetailDrawerProps {
  detail: TradeDetail | null;
  loading: boolean;
  onClose: () => void;
}

export const TradeDetailDrawer: React.FC<TradeDetailDrawerProps> = ({ detail, loading, onClose }) => {
  const statusColor = detail?.trade.status === 'CLOSED' ? 'secondary' 
    : detail?.trade.status === 'POSITION_OPEN' ? 'success' 
    : 'warning';

  return (
    <Drawer 
      anchor="right" 
      open={!!detail || loading} 
      onClose={onClose}
      sx={{ '& .MuiDrawer-paper': { width: { xs: '100%', sm: 500, md: 600 } } }}
    >
      <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', borderBottom: 1, borderColor: 'divider', p: 3, pb: 2 }}>
        <Box>
          <Box sx={{ display: 'flex', alignItems: 'center', gap: 1.5 }}>
            <Typography variant="h6" sx={{ fontWeight: 800 }}>
              Trade Lifecycle {detail ? `#${detail.trade.id}` : ''}
            </Typography>
            {detail && <Chip label={detail.trade.status} color={statusColor} size="small" sx={{ fontWeight: 700 }} />}
          </Box>
          {detail && (
            <Typography variant="caption" color="text.secondary" sx={{ fontFamily: 'monospace' }}>
              {detail.trade.instrument}
            </Typography>
          )}
        </Box>
        <IconButton onClick={onClose} size="small">
          <CloseIcon />
        </IconButton>
      </Box>

      <Box sx={{ p: 3, overflowY: 'auto' }}>
        {loading ? (
          <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'center', py: 8 }}>
            <CircularProgress size={32} sx={{ mr: 2 }} />
            <Typography color="text.secondary">Loading complete lifecycle data...</Typography>
          </Box>
        ) : !detail ? (
          <Typography color="text.secondary" align="center" sx={{ py: 8 }}>No data available</Typography>
        ) : (
          <>
            {/* Metrics */}
            <Grid container spacing={2} sx={{ mb: 4 }}>
              {[
                { label: "Entry Price", value: `₹${detail.trade.entry_price ?? '—'}` },
                { label: "Exit Price", value: `₹${detail.trade.exit_price ?? '—'}` },
                { label: "Quantity", value: detail.trade.quantity },
                { label: "Realized P&L", value: `₹${detail.trade.realized_pnl.toFixed(2)}`, color: detail.trade.realized_pnl >= 0 ? 'success.main' : 'error.main' },
              ].map((m) => (
                <Grid size={{ xs: 6, sm: 3 }} key={m.label}>
                  <Paper variant="outlined" sx={{ p: 2, borderRadius: 2, textAlign: 'center' }}>
                    <Typography variant="caption" color="text.secondary">{m.label}</Typography>
                    <Typography variant="h6" color={m.color || 'text.primary'} sx={{ fontWeight: 700 }}>{m.value}</Typography>
                  </Paper>
                </Grid>
              ))}
            </Grid>

            {/* Timeline */}
            <Typography variant="subtitle2" color="text.secondary" gutterBottom sx={{ display: 'flex', alignItems: 'center', gap: 1, mb: 2 }}>
              ⏱️ Complete End-to-End Lifecycle Sequence
            </Typography>
            <Stepper orientation="vertical" sx={{ mb: 3 }}>
              {detail.timeline.map((step) => (
                <Step key={step.step} active={step.completed} completed={step.completed}>
                  <StepLabel 
                    optional={step.timestamp && <Typography variant="caption" color="text.disabled" sx={{ fontFamily: 'monospace' }}>{formatLocalTime(step.timestamp)}</Typography>}
                  >
                    <Typography variant="body2" sx={{ fontWeight: 600 }}>Step {step.step}: {step.title}</Typography>
                  </StepLabel>
                  <StepContent>
                    <Paper variant="outlined" sx={{ p: 1.5, bgcolor: 'grey.50', borderRadius: 1.5 }}>
                      {Object.entries(step.details).map(([key, val]) => (
                        <Box key={key} sx={{ display: 'flex', justifyContent: 'space-between', py: 0.3, borderBottom: '1px solid', borderColor: 'divider', '&:last-child': { border: 0 } }}>
                          <Typography variant="caption" color="text.secondary" sx={{ textTransform: 'uppercase', letterSpacing: 0.5 }}>
                            {key.replace(/_/g, ' ')}:
                          </Typography>
                          <Typography variant="caption" sx={{ fontFamily: 'monospace' }}>
                            {typeof val === 'object' ? JSON.stringify(val) : String(val ?? '—')}
                          </Typography>
                        </Box>
                      ))}
                    </Paper>
                  </StepContent>
                </Step>
              ))}
            </Stepper>

            {/* Audit Trail */}
            {detail.logs.length > 0 && (
              <Box>
                <Typography variant="subtitle2" color="text.secondary" gutterBottom sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                  📜 Audit Events for Trade #{detail.trade.id}
                </Typography>
                <Paper variant="outlined" sx={{ p: 1.5, maxHeight: 160, overflow: 'auto', bgcolor: 'grey.50' }}>
                  {detail.logs.map((log) => (
                    <Box key={log.id} sx={{ display: 'flex', justifyContent: 'space-between', borderBottom: '1px solid', borderColor: 'divider', py: 0.5, '&:last-child': { border: 0 } }}>
                      <Box>
                        <Typography variant="caption" color="primary.main" sx={{ fontWeight: 700 }}>{log.action}: </Typography>
                        <Typography variant="caption" color="text.secondary">{JSON.stringify(log.details)}</Typography>
                      </Box>
                      <Typography variant="caption" color="text.disabled" sx={{ ml: 1, fontFamily: 'monospace', whiteSpace: 'nowrap' }}>
                        {formatLocalTime(log.timestamp, '')}
                      </Typography>
                    </Box>
                  ))}
                </Paper>
              </Box>
            )}
          </>
        )}
      </Box>
    </Drawer>
  );
};
