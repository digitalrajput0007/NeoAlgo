import type { TradeSignalItem } from '@/types';
import Card from "@mui/material/Card";
import CardContent from "@mui/material/CardContent";
import CardHeader from "@mui/material/CardHeader";
import Typography from "@mui/material/Typography";
import Box from "@mui/material/Box";
import { DataGrid, GridColDef, GridRenderCellParams } from "@mui/x-data-grid";
import { formatLocalTime } from "@/utils/timezone";

interface SignalsTabProps {
  signals: TradeSignalItem[];
}

export function SignalsTab({ signals }: SignalsTabProps) {
  
  const columns: GridColDef[] = [
    { field: 'timestamp', headerName: 'Time', flex: 1.2, minWidth: 150, valueFormatter: (value: any) => value ? formatLocalTime(value as string) : '—' },
    { field: 'underlying', headerName: 'Underlying', flex: 1, minWidth: 120, renderCell: (params: GridRenderCellParams) => <Box sx={{ fontWeight: 700 }}>{params.value || '—'}</Box> },
    { 
      field: 'option', 
      headerName: 'Option', 
      flex: 1.5,
      minWidth: 180, 
      renderCell: (params: GridRenderCellParams) => (
        <Box sx={{ display: 'flex', alignItems: 'center' }}>
          {params.row.strike} {params.row.option_type}
          {params.row.expiry && <Typography variant="caption" sx={{ ml: 1, color: 'text.disabled' }}>{params.row.expiry}</Typography>}
        </Box>
      )
    },
    { 
      field: 'entry_trigger', 
      headerName: 'Entry', 
      flex: 1,
      minWidth: 100, 
      type: 'number',
      renderCell: (params: GridRenderCellParams) => (
        <Box sx={{ bgcolor: 'primary.50', width: '100%', height: '100%', display: 'flex', alignItems: 'center', justifyContent: 'flex-end', px: 1 }}>
          {params.value ? `₹${(params.value as number).toFixed(2)}` : '—'}
        </Box>
      )
    },
    { field: 'target', headerName: 'Target', flex: 1, minWidth: 100, type: 'number', renderCell: (params: GridRenderCellParams) => <Box sx={{ color: 'success.main' }}>{params.value ? `₹${(params.value as number).toFixed(2)}` : '—'}</Box> },
    { field: 'stop_loss', headerName: 'Stop Loss', flex: 1, minWidth: 100, type: 'number', renderCell: (params: GridRenderCellParams) => <Box sx={{ color: 'error.main' }}>{params.value ? `₹${(params.value as number).toFixed(2)}` : '—'}</Box> }
  ];

  return (
    <Card sx={{ animation: 'fadeIn 0.3s' }}>
      <CardHeader 
        title="Trade Signals"
        subheader="Real-time options trading signals received from Telegram."
        sx={{ borderBottom: 1, borderColor: 'divider' }}
      />
      <CardContent>
        <Box sx={{ height: 600, width: '100%' }}>
          <DataGrid
            rows={signals}
            columns={columns}
            initialState={{
              pagination: { paginationModel: { page: 0, pageSize: 50 } },
              sorting: { sortModel: [{ field: 'timestamp', sort: 'desc' }] }
            }}
            pageSizeOptions={[25, 50, 100]}
            disableRowSelectionOnClick
          />
        </Box>
      </CardContent>
    </Card>
  );
}
