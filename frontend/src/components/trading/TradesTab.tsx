import type { TradeItem } from "@/types";
import Card from "@mui/material/Card";
import CardContent from "@mui/material/CardContent";
import CardHeader from "@mui/material/CardHeader";
import Tabs from "@mui/material/Tabs";
import Tab from "@mui/material/Tab";
import Box from "@mui/material/Box";
import { DataGrid, GridColDef, GridRenderCellParams } from "@mui/x-data-grid";
import { StatusBadge } from "@/components/shared/StatusBadge";
import { formatLocalTime } from "@/utils/timezone";

interface TradesTabProps {
  activeTrades: TradeItem[];
  historyTrades: TradeItem[];
  view: 'active' | 'history';
  onViewChange: (view: 'active' | 'history') => void;
  onTradeClick: (trade: TradeItem) => void;
}

export function TradesTab({ activeTrades, historyTrades, view, onViewChange, onTradeClick }: TradesTabProps) {
  
  const columns: GridColDef[] = [
    { field: 'id', headerName: 'ID', width: 80, valueFormatter: (value: any) => `#${value}` },
    { 
      field: 'instrument', 
      headerName: 'Instrument', 
      flex: 1.5, 
      minWidth: 220, 
      renderCell: (params: GridRenderCellParams) => {
        const row = params.row as TradeItem;
        const name = row.underlying && row.strike && row.option_type 
          ? `${row.underlying} ${row.strike} ${row.option_type}` 
          : row.instrument;
        return <Box sx={{ fontWeight: 700 }}>{name}</Box>;
      }
    },
    { field: 'status', headerName: 'Status', flex: 1.2, minWidth: 160, renderCell: (params: GridRenderCellParams) => <StatusBadge status={params.value as string} size="small" /> },
    { field: 'actual_entry', headerName: 'Entry', flex: 1, minWidth: 110, type: 'number', valueFormatter: (value: any) => value ? `₹${value.toFixed(2)}` : '—' },
    { field: 'current_ltp', headerName: 'LTP', flex: 1, minWidth: 110, type: 'number', valueFormatter: (value: any) => value ? `₹${value.toFixed(2)}` : '—' },
    { 
      field: 'realized_pnl', 
      headerName: 'Realized P&L', 
      flex: 1.2,
      minWidth: 140, 
      type: 'number',
      renderCell: (params: GridRenderCellParams) => {
        const val = params.value as number;
        if (!val || val === 0) return '—';
        return (
          <Box sx={{ fontWeight: 800, fontSize: '1rem', color: val > 0 ? 'success.main' : 'error.main' }}>
            ₹{val.toFixed(2)}
          </Box>
        );
      }
    },
    { field: 'created_at', headerName: 'Time', flex: 1, minWidth: 140, valueFormatter: (value: any) => value ? formatLocalTime(value as string) : '—' }
  ];

  const renderDataGrid = (trades: TradeItem[]) => {
    return (
      <Box sx={{ height: 600, width: '100%' }}>
        <DataGrid
          rows={trades}
          columns={columns}
          initialState={{
            pagination: { paginationModel: { page: 0, pageSize: 50 } },
            sorting: { sortModel: [{ field: 'id', sort: 'desc' }] }
          }}
          pageSizeOptions={[25, 50, 100]}
          disableRowSelectionOnClick
          onRowClick={(params) => onTradeClick(params.row as TradeItem)}
          sx={{
            border: 0,
            '& .MuiDataGrid-row': { cursor: 'pointer' }
          }}
        />
      </Box>
    );
  };

  return (
    <Card sx={{ animation: 'fadeIn 0.3s' }}>
      <CardHeader 
        title="Trade Management"
        subheader="View and manage all algo-driven trades."
        action={
          <Tabs 
            value={view} 
            onChange={(_, newValue) => onViewChange(newValue)}
            sx={{ borderBottom: 1, borderColor: 'divider', mt: 1 }}
          >
            <Tab label={`Active Trades (${activeTrades.length})`} value="active" />
            <Tab label="Trade History" value="history" />
          </Tabs>
        }
        sx={{ pb: 0 }}
      />
      <CardContent sx={{ p: 0, '&:last-child': { pb: 0 } }}>
        {view === 'active' ? renderDataGrid(activeTrades) : renderDataGrid(historyTrades)}
      </CardContent>
    </Card>
  );
}
