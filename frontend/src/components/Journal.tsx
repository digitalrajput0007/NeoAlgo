import React, { useEffect, useState } from 'react';
import { api } from '../services/api';
import type { AnalyticsSummary, DailyAnalytics } from '../types';
import Card from "@mui/material/Card";
import CardContent from "@mui/material/CardContent";
import CardHeader from "@mui/material/CardHeader";
import Typography from "@mui/material/Typography";
import Box from "@mui/material/Box";
import Grid from "@mui/material/Grid";
import Tabs from "@mui/material/Tabs";
import Tab from "@mui/material/Tab";
import { DataGrid, GridColDef, GridRenderCellParams } from "@mui/x-data-grid";
import { StatusBadge } from "@/components/shared/StatusBadge";
import { KpiCard } from './shared/KpiCard';
import TrendingUpIcon from "@mui/icons-material/TrendingUp";
import PercentIcon from "@mui/icons-material/Percent";
import GpsFixedIcon from "@mui/icons-material/GpsFixed";
import AutoStoriesIcon from "@mui/icons-material/AutoStories";
import { formatLocalTime } from "@/utils/timezone";
import { 
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip as RechartsTooltip, ResponsiveContainer, Cell
} from 'recharts';

export const Journal: React.FC<{ initialTab?: number }> = ({ initialTab = 0 }) => {
  const [activeTab, setActiveTab] = useState(initialTab);

  useEffect(() => {
    setActiveTab(initialTab);
  }, [initialTab]);
  const [trades, setTrades] = useState<any[]>([]);
  const [totalTrades, setTotalTrades] = useState(0);
  const [paginationModel, setPaginationModel] = useState({ page: 0, pageSize: 25 });
  const [loading, setLoading] = useState(false);

  const [analytics, setAnalytics] = useState<AnalyticsSummary | null>(null);
  const [dailyPnl, setDailyPnl] = useState<DailyAnalytics[]>([]);

  useEffect(() => {
    if (activeTab === 0) {
      setLoading(true);
      api.getJournalTrades(paginationModel.page * paginationModel.pageSize, paginationModel.pageSize)
        .then(res => {
          setTrades(res.items);
          setTotalTrades(res.total);
        })
        .catch(console.error)
        .finally(() => setLoading(false));
    } else {
      api.getAnalytics(30).then(setAnalytics).catch(console.error);
      api.getDailyAnalytics(30).then(setDailyPnl).catch(console.error);
    }
  }, [activeTab, paginationModel]);

  const columns: GridColDef[] = [
    { field: 'id', headerName: 'ID', width: 80, valueFormatter: (value: any) => `#${value}` },
    { field: 'instrument', headerName: 'Instrument', flex: 1.5, minWidth: 150, renderCell: (params: GridRenderCellParams) => <Box sx={{ fontWeight: 700 }}>{params.value || params.row.instrument_token}</Box> },
    { field: 'entry_direction', headerName: 'Type', flex: 0.8, minWidth: 80, renderCell: (params: GridRenderCellParams) => <Box sx={{ fontWeight: 500, color: 'text.secondary' }}>{params.value || 'BUY'}</Box> },
    { field: 'entry_price', headerName: 'Entry', flex: 1, minWidth: 100, type: 'number', valueFormatter: (value: any) => value ? value.toFixed(2) : '—' },
    { field: 'exit_price', headerName: 'Exit', flex: 1, minWidth: 100, type: 'number', valueFormatter: (value: any) => value ? value.toFixed(2) : '—' },
    { field: 'quantity', headerName: 'Qty', flex: 0.8, minWidth: 80, type: 'number', valueFormatter: (value: any) => value || 0 },
    { 
      field: 'realized_pnl', 
      headerName: 'P&L', 
      flex: 1.2,
      minWidth: 130, 
      type: 'number',
      renderCell: (params: GridRenderCellParams) => {
        const val = params.value as number || 0;
        return (
          <Box sx={{ fontWeight: 800, fontSize: '1rem', color: val >= 0 ? 'success.main' : 'error.main' }}>
            {val >= 0 ? '+' : ''}₹{val.toFixed(2)}
          </Box>
        );
      }
    },
    { field: 'status', headerName: 'Status', flex: 1.2, minWidth: 150, renderCell: (params: GridRenderCellParams) => <StatusBadge status={params.value as string} size="small" /> },
    { field: 'created_at', headerName: 'Date', flex: 1.2, minWidth: 150, valueFormatter: (value: any) => value ? formatLocalTime(value as string) : '—' }
  ];

  return (
    <Box sx={{ animation: 'fadeIn 0.3s' }}>
      {activeTab === 0 && (
        <Card elevation={2}>
          <CardHeader
            avatar={<AutoStoriesIcon color="primary" />}
            title="Paper Trade Log"
            sx={{ borderBottom: 1, borderColor: 'divider' }}
          />
          <CardContent sx={{ p: 0, '&:last-child': { pb: 0 } }}>
            <Box sx={{ height: 600, width: '100%' }}>
              <DataGrid
                rows={trades}
                columns={columns}
                rowCount={totalTrades}
                loading={loading}
                pageSizeOptions={[25, 50, 100]}
                paginationModel={paginationModel}
                paginationMode="server"
                onPaginationModelChange={setPaginationModel}
                disableRowSelectionOnClick
                sx={{ border: 0 }}
              />
            </Box>
          </CardContent>
        </Card>
      )}

      {activeTab === 1 && (
        <Box>
          <Grid container spacing={2} sx={{ mb: 3 }}>
            <Grid size={{ xs: 6, md: 3 }}>
              <KpiCard
                label="Realized P&L"
                value={`₹${(analytics?.total_realized_pnl || 0).toFixed(2)}`}
                icon={<TrendingUpIcon fontSize="small" />}
                trend={(analytics?.total_realized_pnl || 0) >= 0 ? 'positive' : 'negative'}
              />
            </Grid>
            <Grid size={{ xs: 6, md: 3 }}>
              <KpiCard
                label="Win Rate"
                value={`${(analytics?.win_rate_percentage || 0).toFixed(1)}%`}
                icon={<PercentIcon fontSize="small" />}
                trend={(analytics?.win_rate_percentage || 0) >= 50 ? 'positive' : 'negative'}
              />
            </Grid>
            <Grid size={{ xs: 6, md: 3 }}>
              <KpiCard
                label="Winning Trades"
                value={analytics?.winning_trades || 0}
                icon={<GpsFixedIcon fontSize="small" />}
                trend="positive"
              />
            </Grid>
            <Grid size={{ xs: 6, md: 3 }}>
              <KpiCard
                label="Total Trades"
                value={analytics?.total_closed_trades || 0}
                icon={<AutoStoriesIcon fontSize="small" />}
                trend="neutral"
              />
            </Grid>
          </Grid>

          <Card elevation={2}>
            <CardHeader
              title="Daily P&L (Last 30 Days)"
              titleTypographyProps={{ variant: 'subtitle2', fontWeight: 'bold' }}
              sx={{ borderBottom: 1, borderColor: 'divider' }}
            />
            <CardContent>
              <Box sx={{ height: 288, width: '100%' }}>
                {dailyPnl.length > 0 ? (
                  <ResponsiveContainer width="100%" height="100%">
                    <BarChart data={[...dailyPnl].reverse()} margin={{ top: 10, right: 10, left: 10, bottom: 20 }}>
                      <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#e2e8f0" />
                      <XAxis 
                        dataKey="date" 
                        axisLine={false}
                        tickLine={false}
                        tick={{ fontSize: 10, fill: '#64748b' }}
                        tickFormatter={(val) => val.substring(5)}
                      />
                      <YAxis 
                        axisLine={false}
                        tickLine={false}
                        tick={{ fontSize: 10, fill: '#64748b' }}
                        tickFormatter={(val) => `₹${val}`}
                      />
                      <RechartsTooltip 
                        cursor={{ fill: '#f1f5f9' }}
                        contentStyle={{ borderRadius: '8px', border: 'none', boxShadow: '0 4px 6px -1px rgb(0 0 0 / 0.1)' }}
                        formatter={(value: any) => [`₹${Number(value).toFixed(2)}`, 'P&L']}
                      />
                      <Bar dataKey="pnl" radius={[4, 4, 0, 0]}>
                        {[...dailyPnl].reverse().map((entry, index) => (
                          <Cell key={`cell-${index}`} fill={entry.pnl >= 0 ? '#10b981' : '#f43f5e'} />
                        ))}
                      </Bar>
                    </BarChart>
                  </ResponsiveContainer>
                ) : (
                  <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: '100%' }}>
                    <Typography variant="body2" color="text.secondary">
                      No analytics data available for the selected period
                    </Typography>
                  </Box>
                )}
              </Box>
            </CardContent>
          </Card>
        </Box>
      )}
    </Box>
  );
};
