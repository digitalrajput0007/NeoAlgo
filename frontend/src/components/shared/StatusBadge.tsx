import Chip from "@mui/material/Chip";
import CheckCircleIcon from "@mui/icons-material/CheckCircle";
import CancelIcon from "@mui/icons-material/Cancel";
import ErrorIcon from "@mui/icons-material/Error";
import AccessTimeIcon from "@mui/icons-material/AccessTime";
import AutorenewIcon from "@mui/icons-material/Autorenew";
import SettingsBackupRestoreIcon from "@mui/icons-material/SettingsBackupRestore";
import ShowChartIcon from "@mui/icons-material/ShowChart";

type StatusType = 
  | 'CONNECTED' | 'RECEIVING_TICKS' | 'SUBSCRIBED' 
  | 'STALE' | 'CONNECTING' | 'DISCONNECTED'
  | 'ACTIVE' | 'PAUSED'
  | 'WAITING_FOR_ENTRY' | 'ENTRY_TRIGGERED' | 'POSITION_OPEN' 
  | 'PARTIAL_PROFIT' | 'TRAILING_STOP' | 'CLOSED' 
  | 'CANCELLED' | 'REJECTED' | 'ERROR';

interface StatusBadgeProps {
  status: string;
  size?: 'small' | 'medium';
}

export function StatusBadge({ status, size = 'small' }: StatusBadgeProps) {
  let icon = <SettingsBackupRestoreIcon />;
  let color: 'success' | 'info' | 'warning' | 'error' | 'default' = 'default';

  switch (status.toUpperCase()) {
    case 'CONNECTED':
    case 'RECEIVING_TICKS':
    case 'ACTIVE':
    case 'CLOSED':
    case 'SUBSCRIBED':
      icon = <CheckCircleIcon />;
      color = "success";
      break;
    case 'POSITION_OPEN':
    case 'PARTIAL_PROFIT':
    case 'TRAILING_STOP':
      icon = <ShowChartIcon />;
      color = "info";
      break;
    case 'WAITING_FOR_ENTRY':
    case 'ENTRY_TRIGGERED':
      icon = <AccessTimeIcon />;
      color = "warning";
      break;
    case 'CONNECTING':
      icon = <AutorenewIcon />;
      color = "warning";
      break;
    case 'STALE':
    case 'PAUSED':
    case 'CANCELLED':
      icon = <ErrorIcon />;
      color = "warning";
      break;
    case 'DISCONNECTED':
    case 'REJECTED':
    case 'ERROR':
      icon = <CancelIcon />;
      color = "error";
      break;
  }

  return (
    <Chip
      icon={icon}
      label={status.replace(/_/g, ' ')}
      color={color}
      size={size}
      variant="outlined"
      sx={{ fontWeight: 600, '& .MuiChip-icon': { fontSize: size === 'small' ? 16 : 20 } }}
    />
  );
}
