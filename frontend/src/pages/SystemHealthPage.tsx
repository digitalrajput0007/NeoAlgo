import { Box, Typography } from "@mui/material";
import { SystemStatus } from "../components/system/SystemStatus";
import type { DashboardSummary } from "@/types";

interface SystemHealthPageProps {
  summary: DashboardSummary | null;
}

export function SystemHealthPage({ summary }: SystemHealthPageProps) {
  return (
    <Box sx={{ animation: 'fadeIn 0.3s' }}>
      <Box sx={{ mb: 3 }}>
        <Typography variant="h5" sx={{ fontWeight: 'bold' }}>System Health</Typography>
        <Typography variant="body2" color="text.secondary">
          Monitor core services, database connections, and external API status.
        </Typography>
      </Box>
      <SystemStatus summary={summary} />
    </Box>
  );
}
