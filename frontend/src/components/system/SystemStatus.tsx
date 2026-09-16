import type { DashboardSummary } from '@/types';
import Card from "@mui/material/Card";
import CardContent from "@mui/material/CardContent";
import CardHeader from "@mui/material/CardHeader";
import Typography from "@mui/material/Typography";
import Box from "@mui/material/Box";
import Grid from "@mui/material/Grid";
import Paper from "@mui/material/Paper";
import { StatusBadge } from "@/components/shared/StatusBadge";
import DnsIcon from "@mui/icons-material/Dns";
import StorageIcon from "@mui/icons-material/Storage";
import SendIcon from "@mui/icons-material/Send";
import CellTowerIcon from "@mui/icons-material/CellTower";
import VerifiedUserIcon from "@mui/icons-material/VerifiedUser";

interface SystemStatusProps {
  summary: DashboardSummary | null;
}

export function SystemStatus({ summary }: SystemStatusProps) {
  const connections = summary?.connections;
  if (!connections) return null;

  const items = [
    { label: "Backend Service", icon: <DnsIcon />, status: connections.database.status, details: "Core Engine API" },
    { label: "Database", icon: <StorageIcon />, status: connections.database.status, details: `Type: ${connections.database.type || 'Unknown'}` },
    { label: "Kotak Neo Broker", icon: <VerifiedUserIcon />, status: connections.kotak.status, details: `Read Only: ${connections.kotak.read_only}` },
    { label: "Telegram Webhook", icon: <SendIcon />, status: connections.telegram.status, details: `Channel: ${connections.telegram.channel}` },
    { label: "SFeed Data Stream", icon: <CellTowerIcon />, status: connections.sfeed.status, details: `Total Ticks: ${connections.sfeed.total_ticks}` },
  ];

  return (
    <Box sx={{ maxWidth: 900, mx: 'auto', animation: 'fadeIn 0.3s' }}>
      <Card elevation={2}>
        <CardHeader
          title="System Diagnostics"
          titleTypographyProps={{ variant: 'subtitle1', fontWeight: 'bold' }}
          sx={{ borderBottom: 1, borderColor: 'divider' }}
        />
        <CardContent sx={{ pt: 3 }}>
          <Grid container spacing={2}>
            {items.map((item) => (
              <Grid size={{ xs: 12, md: 6, lg: 4 }} key={item.label}>
                <Paper variant="outlined" sx={{ p: 2.5, display: 'flex', alignItems: 'flex-start', gap: 2, borderRadius: 2, bgcolor: 'grey.50' }}>
                  <Box sx={{ p: 1, bgcolor: 'background.paper', borderRadius: 1.5, boxShadow: 1, color: 'text.secondary', display: 'flex' }}>
                    {item.icon}
                  </Box>
                  <Box sx={{ flexGrow: 1 }}>
                    <Typography variant="subtitle2" sx={{ fontWeight: 700 }}>{item.label}</Typography>
                    <Typography variant="caption" color="text.secondary" sx={{ mb: 1, fontFamily: 'monospace', display: 'block' }}>
                      {item.details}
                    </Typography>
                    <StatusBadge status={item.status} size="small" />
                  </Box>
                </Paper>
              </Grid>
            ))}
          </Grid>
        </CardContent>
      </Card>
    </Box>
  );
}
