import type { PositionItem } from "@/types";
import Card from "@mui/material/Card";
import CardContent from "@mui/material/CardContent";
import CardHeader from "@mui/material/CardHeader";
import Tabs from "@mui/material/Tabs";
import Tab from "@mui/material/Tab";
import Box from "@mui/material/Box";
import { DataGrid, GridColDef, GridRenderCellParams } from "@mui/x-data-grid";

interface PositionsTabProps {
  positions: PositionItem[];
  historyPositions: PositionItem[];
  view: 'open' | 'history';
  onViewChange: (view: 'open' | 'history') => void;
}

export function PositionsTab({ positions, historyPositions, view, onViewChange }: PositionsTabProps) {
  
  const columns: GridColDef[] = [
    { field: 'instrument', headerName: 'Instrument', flex: 1.5, minWidth: 200, renderCell: (params: GridRenderCellParams) => <Box sx={{ fontWeight: 700 }}>{params.value}</Box> },
    { field: 'quantity', headerName: 'Quantity', flex: 0.8, minWidth: 100, type: 'number' },
    { field: 'average_entry', headerName: 'Entry', flex: 1, minWidth: 120, type: 'number', valueFormatter: (value: any) => value ? `₹${value.toFixed(2)}` : '—' },
    { 
      field: 'current_ltp', 
      headerName: 'LTP', 
      flex: 1,
      minWidth: 120, 
      type: 'number', 
      renderCell: (params: GridRenderCellParams) => (
        <Box sx={{ bgcolor: 'grey.50', width: '100%', height: '100%', display: 'flex', alignItems: 'center', justifyContent: 'flex-end', px: 1 }}>
          {params.value ? `₹${(params.value as number).toFixed(2)}` : '—'}
        </Box>
      ) 
    },
    { 
      field: 'unrealized_pnl', 
      headerName: 'Unrealized P&L', 
      flex: 1.2,
      minWidth: 140, 
      type: 'number',
      renderCell: (params: GridRenderCellParams) => {
        const val = params.value as number;
        if (!val || val === 0) return '—';
        return (
          <Box sx={{ fontWeight: 700, color: val > 0 ? 'success.main' : 'error.main' }}>
            ₹{val.toFixed(2)}
          </Box>
        );
      }
    }
  ];

  const renderDataGrid = (posList: PositionItem[]) => {
    return (
      <Box sx={{ height: 600, width: '100%' }}>
        <DataGrid
          rows={posList}
          columns={columns}
          initialState={{
            pagination: { paginationModel: { page: 0, pageSize: 50 } },
          }}
          pageSizeOptions={[25, 50, 100]}
          disableRowSelectionOnClick
        />
      </Box>
    );
  };

  return (
    <Card sx={{ animation: 'fadeIn 0.3s' }}>
      <CardHeader 
        title="Positions"
        subheader="Track open and closed broker positions."
        action={
          <Tabs 
            value={view} 
            onChange={(_, newValue) => onViewChange(newValue)}
            sx={{ borderBottom: 1, borderColor: 'divider', mt: 1 }}
          >
            <Tab label={`Open Positions (${positions.length})`} value="open" />
            <Tab label="Position History" value="history" />
          </Tabs>
        }
        sx={{ pb: 0 }}
      />
      <CardContent>
        {view === 'open' ? renderDataGrid(positions) : renderDataGrid(historyPositions)}
      </CardContent>
    </Card>
  );
}
