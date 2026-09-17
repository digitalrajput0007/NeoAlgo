import type { OrderItem } from "@/types";
import Card from "@mui/material/Card";
import CardContent from "@mui/material/CardContent";
import CardHeader from "@mui/material/CardHeader";
import Tabs from "@mui/material/Tabs";
import Tab from "@mui/material/Tab";
import Box from "@mui/material/Box";
import Chip from "@mui/material/Chip";
import { DataGrid, GridColDef, GridRenderCellParams } from "@mui/x-data-grid";
import { StatusBadge } from "@/components/shared/StatusBadge";
import { formatLocalTime } from "@/utils/timezone";

interface OrdersTabProps {
  orders: OrderItem[];
  historyOrders: OrderItem[];
  view: 'current' | 'history';
  onViewChange: (view: 'current' | 'history') => void;
}

export function OrdersTab({ orders, historyOrders, view, onViewChange }: OrdersTabProps) {
  
  const columns: GridColDef[] = [
    { field: 'broker_order_id', headerName: 'Broker ID', flex: 1.2, minWidth: 150, renderCell: (params: GridRenderCellParams) => <Box sx={{ fontFamily: 'monospace', fontSize: '0.875rem', color: 'text.secondary' }}>{params.value}</Box> },
    { field: 'trade_id', headerName: 'Trade ID', flex: 0.8, minWidth: 100, renderCell: (params: GridRenderCellParams) => <Box sx={{ fontFamily: 'monospace', color: 'text.secondary' }}>#{params.value}</Box> },
    { 
      field: 'order_type', 
      headerName: 'Type', 
      flex: 1,
      minWidth: 100, 
      renderCell: (params: GridRenderCellParams) => (
        <Chip 
          label={params.value as string} 
          size="small" 
          color={params.value === 'BUY' ? 'info' : 'error'} 
          variant="filled"
          sx={{ fontWeight: 'bold', height: 20, fontSize: '0.7rem' }}
        />
      )
    },
    { field: 'status', headerName: 'Status', flex: 1.2, minWidth: 150, renderCell: (params: GridRenderCellParams) => <StatusBadge status={params.value as string} size="small" /> },
    { field: 'quantity', headerName: 'Qty', flex: 0.8, minWidth: 80, type: 'number' },
    { field: 'price', headerName: 'Price', flex: 1, minWidth: 100, type: 'number', valueFormatter: (value: any) => value ? `₹${value.toFixed(2)}` : '—' },
    { field: 'created_at', headerName: 'Time', flex: 1, minWidth: 140, valueFormatter: (value: any) => value ? formatLocalTime(value as string) : '—' }
  ];

  const renderDataGrid = (orderList: OrderItem[]) => {
    return (
      <Box sx={{ height: 600, width: '100%' }}>
        <DataGrid
          rows={orderList}
          columns={columns}
          initialState={{
            pagination: { paginationModel: { page: 0, pageSize: 50 } },
            sorting: { sortModel: [{ field: 'created_at', sort: 'desc' }] }
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
        title="Orders"
        subheader="Track pending and executed broker orders."
        action={
          <Tabs 
            value={view} 
            onChange={(_, newValue) => onViewChange(newValue)}
            sx={{ borderBottom: 1, borderColor: 'divider', mt: 1 }}
          >
            <Tab label={`Current Orders (${orders.length})`} value="current" />
            <Tab label="Order History" value="history" />
          </Tabs>
        }
        sx={{ pb: 0 }}
      />
      <CardContent>
        {view === 'current' ? renderDataGrid(orders) : renderDataGrid(historyOrders)}
      </CardContent>
    </Card>
  );
}
