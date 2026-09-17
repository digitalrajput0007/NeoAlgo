import type { TradeItem, PositionItem } from '@/types';
import Table from "@mui/material/Table";
import TableBody from "@mui/material/TableBody";
import TableCell from "@mui/material/TableCell";
import TableContainer from "@mui/material/TableContainer";
import TableHead from "@mui/material/TableHead";
import TableRow from "@mui/material/TableRow";
import Paper from "@mui/material/Paper";
import Typography from "@mui/material/Typography";
import { StatusBadge } from "@/components/shared/StatusBadge";
import { EmptyState } from "@/components/shared/EmptyState";
import ActivityIcon from "@mui/icons-material/ShowChart";

interface ActiveTradesTableProps {
  trades: TradeItem[];
  positions: PositionItem[];
  onTradeClick: (trade: TradeItem) => void;
}

export function ActiveTradesTable({ trades, positions, onTradeClick }: ActiveTradesTableProps) {
  if (trades.length === 0) {
    return (
      <EmptyState
        title="No Active Trades"
        description="No trades are currently waiting or active."
        icon={<ActivityIcon />}
      />
    );
  }

  return (
    <TableContainer component={Paper} elevation={1} sx={{ borderRadius: 2, maxHeight: 350, overflowY: 'auto' }}>
      <Table size="small" stickyHeader>
        <TableHead sx={{ bgcolor: 'grey.50' }}>
          <TableRow>
            <TableCell sx={{ fontWeight: 600 }}>Trade</TableCell>
            <TableCell sx={{ fontWeight: 600 }}>Instrument</TableCell>
            <TableCell sx={{ fontWeight: 600 }}>Status</TableCell>
            <TableCell align="right" sx={{ fontWeight: 600 }}>Qty</TableCell>
            <TableCell align="right" sx={{ fontWeight: 600 }}>Entry</TableCell>
            <TableCell align="right" sx={{ fontWeight: 700, color: 'warning.dark' }}>LTP</TableCell>
            <TableCell align="right" sx={{ fontWeight: 600, color: 'error.main' }}>SL</TableCell>
            <TableCell align="right" sx={{ fontWeight: 600, color: 'success.main' }}>Target</TableCell>
            <TableCell align="right" sx={{ fontWeight: 600 }}>P&L</TableCell>
            <TableCell align="right" sx={{ fontWeight: 600 }}>Time</TableCell>
          </TableRow>
        </TableHead>
        <TableBody>
          {trades.map((trade) => {
            const pos = positions.find(p => p.instrument_token === trade.instrument && p.quantity !== 0);
            const unrealizedPnl = pos?.unrealized_pnl || 0;
            const ltp = pos?.current_ltp || trade.current_ltp || trade.actual_entry || 0;

            return (
              <TableRow 
                key={trade.id} 
                hover
                onClick={() => onTradeClick(trade)}
                sx={{ cursor: 'pointer', '&:last-child td, &:last-child th': { border: 0 } }}
              >
                <TableCell sx={{ color: 'text.secondary' }}>#{trade.id}</TableCell>
                <TableCell sx={{ fontWeight: 700 }}>
                  {trade.underlying && trade.strike && trade.option_type 
                    ? `${trade.underlying} ${trade.strike} ${trade.option_type}` 
                    : trade.instrument}
                </TableCell>
                <TableCell>
                  <StatusBadge status={trade.status} size="small" />
                </TableCell>
                <TableCell align="right" sx={{ fontFamily: 'monospace' }}>
                  {trade.quantity || '-'}
                </TableCell>
                <TableCell align="right" sx={{ fontFamily: 'monospace' }}>
                  {trade.actual_entry ? `₹${trade.actual_entry.toFixed(2)}` : '—'}
                </TableCell>
                <TableCell align="right" sx={{ fontFamily: 'monospace', fontWeight: 700, bgcolor: 'warning.50' }}>
                  {ltp > 0 ? `₹${ltp.toFixed(2)}` : '—'}
                </TableCell>
                <TableCell align="right" sx={{ fontFamily: 'monospace', color: 'text.secondary' }}>
                  {trade.stop_loss ? `₹${trade.stop_loss.toFixed(2)}` : '—'}
                </TableCell>
                <TableCell align="right" sx={{ fontFamily: 'monospace', color: 'text.secondary' }}>
                  {trade.target ? `₹${trade.target.toFixed(2)}` : '—'}
                </TableCell>
                <TableCell align="right" sx={{ fontFamily: 'monospace' }}>
                  {trade.status === 'WAITING_FOR_ENTRY' ? '—' : (
                    <Typography
                      variant="body2" 
                      color={unrealizedPnl >= 0 ? "success.main" : "error.main"}
                      sx={{ fontWeight: 700, fontFamily: 'monospace' }}
                    >
                      {unrealizedPnl >= 0 ? '+' : ''}₹{unrealizedPnl.toFixed(2)}
                    </Typography>
                  )}
                </TableCell>
                <TableCell align="right" sx={{ color: 'text.disabled', fontSize: '0.75rem' }}>
                  {trade.created_at ? new Date(trade.created_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' }) : '—'}
                </TableCell>
              </TableRow>
            );
          })}
        </TableBody>
      </Table>
    </TableContainer>
  );
}
