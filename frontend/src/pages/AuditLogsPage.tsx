import { useState, useEffect } from 'react';
import { Box, Card, CardContent, CardHeader, Typography, Chip } from "@mui/material";
import { DataGrid, GridColDef, GridRenderCellParams } from "@mui/x-data-grid";
import { api } from "../services/api";
import type { AuditLogItem } from "../types";
import { formatLocalTime } from "../utils/timezone";

// Human-readable labels for audit actions
const ACTION_LABELS: Record<string, { label: string; color: 'primary' | 'success' | 'warning' | 'error' | 'info' | 'default' }> = {
  'TRADING_PAUSED':           { label: 'Trading Paused',         color: 'warning' },
  'TRADING_RESUMED':          { label: 'Trading Resumed',        color: 'success' },
  'EMERGENCY_CLOSE_ALL':      { label: 'Emergency Close All',    color: 'error' },
  'RISK_CONFIG_UPDATED':      { label: 'Risk Config Updated',    color: 'info' },
  'PAPER_STATE_RESET':        { label: 'Paper State Reset',      color: 'warning' },
  'ENTRY_TIMEOUT_CANCELLED':  { label: 'Entry Timeout',          color: 'default' },
  'TRADE_REJECTED':           { label: 'Trade Rejected',         color: 'error' },
  'TRADE_OPENED':             { label: 'Trade Opened',           color: 'success' },
  'TRADE_CLOSED':             { label: 'Trade Closed',           color: 'primary' },
  'SIGNAL_RECEIVED':          { label: 'Signal Received',        color: 'info' },
  'ORDER_PLACED':             { label: 'Order Placed',           color: 'success' },
  'POSITION_OPENED':          { label: 'Position Opened',        color: 'success' },
  'POSITION_CLOSED':          { label: 'Position Closed',        color: 'primary' },
  'PASSWORD_CHANGED':         { label: 'Password Changed',       color: 'warning' },
  'LOGIN':                    { label: 'Login',                   color: 'info' },
  'LOGOUT':                   { label: 'Logout',                  color: 'default' },
};

function formatActionLabel(action: string): { label: string; color: 'primary' | 'success' | 'warning' | 'error' | 'info' | 'default' } {
  if (ACTION_LABELS[action]) return ACTION_LABELS[action];
  // Fallback: convert SNAKE_CASE to Title Case
  const label = action
    .split('_')
    .map(word => word.charAt(0).toUpperCase() + word.slice(1).toLowerCase())
    .join(' ');
  // Infer color from keywords
  let color: 'primary' | 'success' | 'warning' | 'error' | 'info' | 'default' = 'default';
  if (action.includes('ERROR') || action.includes('REJECT') || action.includes('EMERGENCY')) color = 'error';
  else if (action.includes('PAUSE') || action.includes('RESET') || action.includes('CANCEL')) color = 'warning';
  else if (action.includes('OPEN') || action.includes('RESUME') || action.includes('SUCCESS')) color = 'success';
  else if (action.includes('SIGNAL') || action.includes('UPDATE') || action.includes('CONFIG')) color = 'info';
  return { label, color };
}

function simplifyDetails(description: string): string {
  if (!description || description === 'None' || description === 'null') return '—';
  
  // Try to parse as JSON dict and extract key values
  try {
    // The backend sends str(l.details), which for dicts looks like: {'key': 'value', ...}
    // or could be a proper JSON string
    let parsed: any;
    if (description.startsWith('{') || description.startsWith('[')) {
      // Try JSON first, then Python dict format
      try {
        parsed = JSON.parse(description);
      } catch {
        // Python dict format: replace single quotes with double quotes
        const jsonified = description
          .replace(/'/g, '"')
          .replace(/True/g, 'true')
          .replace(/False/g, 'false')
          .replace(/None/g, 'null');
        parsed = JSON.parse(jsonified);
      }
    }

    if (parsed && typeof parsed === 'object' && !Array.isArray(parsed)) {
      // Build a clean summary from key fields
      const parts: string[] = [];
      const keys = Object.keys(parsed);
      
      for (const key of keys) {
        const val = parsed[key];
        if (val === null || val === undefined || val === '') continue;
        // Format key: snake_case → Title Case
        const readableKey = key.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase());
        // Truncate long values
        const strVal = typeof val === 'object' ? JSON.stringify(val) : String(val);
        parts.push(`${readableKey}: ${strVal.length > 80 ? strVal.slice(0, 80) + '…' : strVal}`);
      }
      return parts.join(' · ') || '—';
    }
  } catch {
    // Not parseable — return as-is but clean up
  }

  // Plain string — just clean up
  return description.length > 200 ? description.slice(0, 200) + '…' : description;
}

export function AuditLogsPage() {
  const [logs, setLogs] = useState<AuditLogItem[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const fetchLogs = async () => {
      try {
        const data = await api.getAuditLogs();
        setLogs(data);
      } catch (err) {
        console.error("Failed to fetch audit logs:", err);
      } finally {
        setLoading(false);
      }
    };
    fetchLogs();
  }, []);

  const columns: GridColDef[] = [
    { field: 'id', headerName: 'ID', width: 80, valueFormatter: (value: any) => `#${value}` },
    { field: 'timestamp', headerName: 'Time', width: 160, valueFormatter: (value: any) => value ? formatLocalTime(value as string) : '—' },
    { 
      field: 'event', 
      headerName: 'Action', 
      width: 200,
      renderCell: (params: GridRenderCellParams) => {
        const raw = (params.value as string) || '';
        const { label, color } = formatActionLabel(raw);
        return (
          <Chip 
            label={label} 
            size="small" 
            color={color}
            variant="filled" 
            sx={{ fontWeight: 600, fontSize: '0.75rem' }} 
          />
        );
      }
    },
    { 
      field: 'description', 
      headerName: 'Details', 
      flex: 2,
      minWidth: 300, 
      renderCell: (params: GridRenderCellParams) => {
        const simplified = simplifyDetails(String(params.value || ''));
        return (
          <Box sx={{ 
            fontSize: '0.8rem', 
            color: 'text.secondary', 
            whiteSpace: 'normal', 
            wordBreak: 'break-word',
            lineHeight: 1.5,
            py: 1 
          }}>
            {simplified}
          </Box>
        );
      }
    }
  ];

  return (
    <Box sx={{ animation: 'fadeIn 0.3s' }}>
      <Box sx={{ mb: 3 }}>
        <Typography variant="h5" sx={{ fontWeight: 'bold' }}>Audit Logs</Typography>
        <Typography variant="body2" color="text.secondary">
          Track system events, state changes, and critical operations.
        </Typography>
      </Box>

      <Card>
        <CardHeader 
          title="Recent Activity" 
          sx={{ borderBottom: 1, borderColor: 'divider' }}
        />
        <CardContent sx={{ p: 0, '&:last-child': { pb: 0 } }}>
          <Box sx={{ height: 600, width: '100%' }}>
            <DataGrid
              rows={logs}
              columns={columns}
              loading={loading}
              initialState={{
                pagination: { paginationModel: { page: 0, pageSize: 50 } },
                sorting: { sortModel: [{ field: 'id', sort: 'desc' }] }
              }}
              pageSizeOptions={[25, 50, 100]}
              disableRowSelectionOnClick
              getRowHeight={() => 'auto'}
              sx={{ border: 0 }}
            />
          </Box>
        </CardContent>
      </Card>
    </Box>
  );
}
