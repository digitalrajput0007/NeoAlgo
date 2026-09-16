import type { DashboardSummary } from '@/types';
import { api } from "@/services/api";
import Card from "@mui/material/Card";
import CardContent from "@mui/material/CardContent";
import CardHeader from "@mui/material/CardHeader";
import Typography from "@mui/material/Typography";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Chip from "@mui/material/Chip";
import Divider from "@mui/material/Divider";
import Dialog from "@mui/material/Dialog";
import DialogActions from "@mui/material/DialogActions";
import DialogContent from "@mui/material/DialogContent";
import DialogContentText from "@mui/material/DialogContentText";
import DialogTitle from "@mui/material/DialogTitle";
import PlayCircleIcon from "@mui/icons-material/PlayCircle";
import StopCircleIcon from "@mui/icons-material/StopCircle";
import WarningAmberIcon from "@mui/icons-material/WarningAmber";
import DangerousIcon from "@mui/icons-material/Dangerous";
import { useState } from "react";

interface OperationalControlsProps {
  summary: DashboardSummary | null;
  refreshData: () => void;
}

export function OperationalControls({ summary, refreshData }: OperationalControlsProps) {
  const [isPending, setIsPending] = useState(false);
  const [openDialog, setOpenDialog] = useState(false);
  const isPaused = summary?.metrics?.new_trades_paused ?? false;

  const handlePauseResume = async () => {
    setIsPending(true);
    try {
      if (isPaused) {
        await api.resumeNewTrades();
      } else {
        await api.pauseNewTrades();
      }
      refreshData();
    } catch (e) {
      console.error(e);
    } finally {
      setIsPending(false);
    }
  };

  const handleEmergencyClose = async () => {
    setIsPending(true);
    try {
      await api.emergencyCloseAll();
      refreshData();
    } catch (e) {
      console.error(e);
    } finally {
      setIsPending(false);
      setOpenDialog(false);
    }
  };

  return (
    <Box sx={{ maxWidth: 900, mx: 'auto', animation: 'fadeIn 0.3s' }}>
      <Card elevation={2}>
        <CardHeader
          title="Operational Controls"
          subheader="Manage trading session state and emergency actions. All actions are strictly constrained to PAPER mode."
          sx={{ borderBottom: 1, borderColor: 'divider' }}
        />
        <CardContent sx={{ pt: 4 }}>
          
          <Box sx={{ display: 'flex', flexDirection: { xs: 'column', md: 'row' }, alignItems: { md: 'center' }, justifyContent: 'space-between', gap: 3 }}>
            <Box sx={{ maxWidth: 450 }}>
              <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mb: 0.5 }}>
                <Typography variant="subtitle1" sx={{ fontWeight: 700 }}>New Trades Status</Typography>
                <Chip 
                  label={isPaused ? "Paused" : "Active"} 
                  size="small" 
                  color={isPaused ? "error" : "success"} 
                  variant="outlined"
                  sx={{ fontWeight: 700, height: 22, fontSize: '0.7rem' }}
                />
              </Box>
              <Typography variant="body2" color="text.secondary">
                {isPaused 
                  ? "The system will ignore all incoming signals. Existing open positions and trailing stops will continue to be managed normally."
                  : "The system is actively processing new signals and creating trades."}
              </Typography>
            </Box>
            
            <Button 
              variant="contained"
              size="large"
              color={isPaused ? "success" : "inherit"}
              startIcon={isPaused ? <PlayCircleIcon /> : <StopCircleIcon />}
              onClick={handlePauseResume}
              disabled={isPending}
            >
              {isPaused ? 'Resume Trading' : 'Pause New Trades'}
            </Button>
          </Box>

          <Divider sx={{ my: 4 }} />

          <Box sx={{ display: 'flex', flexDirection: { xs: 'column', md: 'row' }, alignItems: { md: 'center' }, justifyContent: 'space-between', gap: 3 }}>
            <Box sx={{ maxWidth: 450 }}>
              <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mb: 0.5 }}>
                <WarningAmberIcon color="error" fontSize="small" />
                <Typography variant="subtitle1" color="error.main" sx={{ fontWeight: 700 }}>Emergency Close All</Typography>
              </Box>
              <Typography variant="body2" color="text.secondary">
                Immediately exit all open positions at market price and cancel all waiting orders. This action cannot be undone.
              </Typography>
            </Box>

            <Button 
              variant="contained"
              size="large"
              color="error"
              startIcon={<DangerousIcon />}
              onClick={() => setOpenDialog(true)}
              disabled={isPending}
            >
              EMERGENCY CLOSE ALL
            </Button>
          </Box>

          <Dialog open={openDialog} onClose={() => setOpenDialog(false)}>
            <DialogTitle sx={{ color: 'error.main', display: 'flex', alignItems: 'center', gap: 1 }}>
              <WarningAmberIcon /> Are you absolutely sure?
            </DialogTitle>
            <DialogContent>
              <DialogContentText>
                This will immediately close all active PAPER positions at the current market price and cancel all waiting signals.
                <br /><br />
                <strong>This action cannot be undone.</strong>
              </DialogContentText>
            </DialogContent>
            <DialogActions>
              <Button onClick={() => setOpenDialog(false)}>Cancel</Button>
              <Button onClick={handleEmergencyClose} variant="contained" color="error">
                Yes, Close All Positions
              </Button>
            </DialogActions>
          </Dialog>
        </CardContent>
      </Card>
    </Box>
  );
}
