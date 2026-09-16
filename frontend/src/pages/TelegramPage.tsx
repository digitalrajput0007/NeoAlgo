import { useState } from 'react';
import Box from '@mui/material/Box';
import Grid from '@mui/material/Grid';
import Card from '@mui/material/Card';
import Typography from '@mui/material/Typography';
import Button from '@mui/material/Button';
import CircularProgress from '@mui/material/CircularProgress';
import Chip from '@mui/material/Chip';
import Dialog from '@mui/material/Dialog';
import DialogTitle from '@mui/material/DialogTitle';
import DialogContent from '@mui/material/DialogContent';
import DialogActions from '@mui/material/DialogActions';
import TextField from '@mui/material/TextField';
import Alert from '@mui/material/Alert';
import { DataGrid, GridColDef } from '@mui/x-data-grid';
import { TelegramStatus, StoredTelegramMessage } from '@/types';
import { api } from '@/services/api';

interface TelegramPageProps {
  status: TelegramStatus | null;
  messages: StoredTelegramMessage[];
  onRefreshData: () => void;
  onOpenChannelSelector: () => void;
}

export function TelegramPage({ status, messages, onRefreshData, onOpenChannelSelector }: TelegramPageProps) {
  const [loadingAction, setLoadingAction] = useState<string | null>(null);

  // Auth Dialog State
  const [authDialogOpen, setAuthDialogOpen] = useState(false);
  const [authStep, setAuthStep] = useState<'phone' | 'code'>('phone');
  const [authPhone, setAuthPhone] = useState('');
  const [authCode, setAuthCode] = useState('');
  const [authPassword, setAuthPassword] = useState('');
  const [authError, setAuthError] = useState<string | null>(null);
  const [authLoading, setAuthLoading] = useState(false);

  const handleAction = async (action: 'connect' | 'disconnect' | 'reconnect' | 'logout') => {
    setLoadingAction(action);
    try {
      if (action === 'connect') {
        if (!status?.authenticated) {
           // Show login dialog
           setAuthStep('phone');
           setAuthPhone('');
           setAuthCode('');
           setAuthPassword('');
           setAuthError(null);
           setAuthDialogOpen(true);
        } else {
           await api.connectTelegram();
        }
      }
      if (action === 'disconnect') await api.disconnectTelegram();
      if (action === 'reconnect') await api.reconnectTelegram();
      if (action === 'logout') await api.logoutTelegram();
      
      onRefreshData();
    } catch (err) {
      console.error(`Failed to ${action} telegram:`, err);
    } finally {
      setLoadingAction(null);
    }
  };

  const handleSendCode = async () => {
    setAuthError(null);
    setAuthLoading(true);
    try {
      await api.sendTelegramCode(authPhone);
      setAuthStep('code');
    } catch (err: any) {
      setAuthError(err.message || 'Failed to send code');
    } finally {
      setAuthLoading(false);
    }
  };

  const handleSignIn = async () => {
    setAuthError(null);
    setAuthLoading(true);
    try {
      await api.signInTelegram(authPhone, authCode, authPassword || undefined);
      setAuthDialogOpen(false);
      onRefreshData();
    } catch (err: any) {
      setAuthError(err.message || 'Failed to sign in');
    } finally {
      setAuthLoading(false);
    }
  };

  const isConnected = status?.connected;
  const isAuthenticated = status?.authenticated;
  const isListenerRunning = status?.listener_status === 'RUNNING';

  const columns: GridColDef[] = [
    { field: 'received_at', headerName: 'Time', flex: 1.2, minWidth: 160, valueFormatter: (params: any) => new Date(params).toLocaleString() },
    { field: 'telegram_message_id', headerName: 'Message ID', flex: 1, minWidth: 130 },
    { field: 'channel_id', headerName: 'Channel', flex: 1, minWidth: 150 },
    { field: 'message_text', headerName: 'Message Preview', flex: 2, minWidth: 200 },
    { 
      field: 'parsed_successfully', 
      headerName: 'Parser Status', 
      flex: 1,
      minWidth: 140,
      renderCell: (params) => (
        <Chip 
          size="small" 
          label={params.value ? "SUCCESS" : "FAILED"} 
          color={params.value ? "success" : "error"} 
          variant="outlined" 
        />
      )
    },
    { field: 'trade_id', headerName: 'Trade ID', flex: 0.8, minWidth: 100 },
  ];

  return (
    <Box sx={{ animation: 'fadeIn 0.3s' }}>
      <Typography variant="h5" sx={{ fontWeight: 700, mb: 3 }}>Telegram Integration</Typography>

      <Grid container spacing={3} sx={{ mb: 4 }}>
        {/* Connection Controls */}
        <Grid size={{ xs: 12, md: 6 }}>
          <Card sx={{ p: 3, height: '100%' }}>
            <Typography variant="subtitle1" sx={{ fontWeight: 700, mb: 2 }}>Connection Status</Typography>
            <Box sx={{ display: 'flex', alignItems: 'center', mb: 3 }}>
              <Typography variant="body1" sx={{ mr: 2 }}>Status:</Typography>
              <Chip 
                label={status?.listener_status || "DISCONNECTED"} 
                color={
                  status?.listener_status === 'RUNNING' ? 'success' : 
                  status?.listener_status === 'WAITING_FOR_CHANNEL' ? 'warning' :
                  'error'
                } 
                sx={{ fontWeight: 700 }}
              />
            </Box>
            
            <Box sx={{ display: 'flex', gap: 2 }}>
              {isAuthenticated ? (
                <>
                  {!isListenerRunning ? (
                    <Button 
                      variant="contained" 
                      color="primary" 
                      onClick={() => handleAction('connect')}
                      disabled={!!loadingAction}
                    >
                      {loadingAction === 'connect' ? <CircularProgress size={24} color="inherit" /> : 'Start Listener'}
                    </Button>
                  ) : (
                    <>
                      <Button 
                        variant="outlined" 
                        color="error" 
                        onClick={() => handleAction('disconnect')}
                        disabled={!!loadingAction}
                      >
                        {loadingAction === 'disconnect' ? <CircularProgress size={24} /> : 'Stop Listener'}
                      </Button>
                      <Button 
                        variant="contained" 
                        color="primary" 
                        onClick={() => handleAction('reconnect')}
                        disabled={!!loadingAction}
                      >
                        {loadingAction === 'reconnect' ? <CircularProgress size={24} color="inherit" /> : 'Restart Listener'}
                      </Button>
                    </>
                  )}
                  <Button 
                    variant="outlined" 
                    color="secondary" 
                    onClick={() => handleAction('logout')}
                    disabled={!!loadingAction}
                    sx={{ ml: 'auto' }}
                  >
                    {loadingAction === 'logout' ? <CircularProgress size={24} /> : 'Logout Account'}
                  </Button>
                </>
              ) : (
                <Button 
                  variant="contained" 
                  color="primary" 
                  onClick={() => handleAction('connect')}
                  disabled={!!loadingAction}
                >
                  {loadingAction === 'connect' ? <CircularProgress size={24} color="inherit" /> : 'Login to Telegram'}
                </Button>
              )}
            </Box>
          </Card>
        </Grid>

        {/* Selected Channel */}
        <Grid size={{ xs: 12, md: 6 }}>
          <Card sx={{ p: 3, height: '100%', opacity: isAuthenticated ? 1 : 0.6 }}>
            <Typography variant="subtitle1" sx={{ fontWeight: 700, mb: 2 }}>Selected Channel</Typography>
            {!isAuthenticated ? (
              <Box sx={{ mb: 3 }}>
                <Typography variant="body2" color="text.secondary">
                  Please login to Telegram to select and manage channels.
                </Typography>
              </Box>
            ) : status?.selected_channel ? (
              <Box>
                <Typography variant="body1" sx={{ fontWeight: 600, mb: 0.5 }}>
                  {status.selected_channel.channel_name || "Unknown Channel"}
                </Typography>
                <Typography variant="body2" color="text.secondary" sx={{ mb: 2, fontFamily: 'monospace' }}>
                  ID: {status.selected_channel.channel_id}
                </Typography>
                
                <Box sx={{ display: 'flex', alignItems: 'center', mb: 3 }}>
                  <Typography variant="body2" sx={{ mr: 1 }}>Listener:</Typography>
                  <Chip 
                    size="small"
                    label={isListenerRunning ? "ACTIVE" : "INACTIVE"} 
                    color={isListenerRunning ? "success" : "warning"} 
                    variant="outlined"
                  />
                </Box>
              </Box>
            ) : (
              <Box sx={{ mb: 3 }}>
                <Typography variant="body1" color="error" sx={{ fontWeight: 600, mb: 1 }}>
                  ⚠ No signal channel selected
                </Typography>
                <Typography variant="body2" color="text.secondary">
                  You must select a channel to receive signals.
                </Typography>
              </Box>
            )}

            <Button variant="outlined" onClick={onOpenChannelSelector} disabled={!isAuthenticated}>
              Choose Channel
            </Button>
          </Card>
        </Grid>
      </Grid>

      {/* Recent Messages */}
      <Typography variant="h6" sx={{ fontWeight: 700, mb: 2 }}>Recent Messages</Typography>
      <Card sx={{ height: 500, width: '100%' }}>
        <DataGrid
          rows={messages}
          columns={columns}
          initialState={{
            pagination: {
              paginationModel: { page: 0, pageSize: 50 },
            },
          }}
          pageSizeOptions={[10, 25, 50, 100]}
          disableRowSelectionOnClick
          density="compact"
        />
      </Card>
      {/* Telegram Auth Dialog */}
      <Dialog open={authDialogOpen} onClose={() => !authLoading && setAuthDialogOpen(false)} maxWidth="sm" fullWidth>
        <DialogTitle>Connect Telegram Account</DialogTitle>
        <DialogContent>
          {authError && <Alert severity="error" sx={{ mb: 2 }}>{authError}</Alert>}
          <Typography variant="body2" sx={{ mb: 3 }}>
            Connect your Telegram account to listen for trading signals.
          </Typography>

          {authStep === 'phone' ? (
            <TextField
              autoFocus
              fullWidth
              label="Phone Number"
              placeholder="+91..."
              value={authPhone}
              onChange={(e) => setAuthPhone(e.target.value)}
              disabled={authLoading}
              helperText="Include country code (e.g., +91 for India)"
            />
          ) : (
            <>
              <TextField
                autoFocus
                fullWidth
                label="OTP Code"
                value={authCode}
                onChange={(e) => setAuthCode(e.target.value)}
                disabled={authLoading}
                sx={{ mb: 2 }}
                helperText="Enter the code sent to your Telegram app"
              />
              <TextField
                fullWidth
                label="2FA Password (Optional)"
                type="password"
                value={authPassword}
                onChange={(e) => setAuthPassword(e.target.value)}
                disabled={authLoading}
                helperText="If you have Two-Step Verification enabled"
              />
            </>
          )}
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setAuthDialogOpen(false)} disabled={authLoading}>Cancel</Button>
          {authStep === 'phone' ? (
            <Button 
              variant="contained" 
              onClick={handleSendCode} 
              disabled={authLoading || !authPhone.trim()}
            >
              {authLoading ? <CircularProgress size={20} color="inherit" /> : 'Send Code'}
            </Button>
          ) : (
            <Button 
              variant="contained" 
              onClick={handleSignIn} 
              disabled={authLoading || !authCode.trim()}
            >
              {authLoading ? <CircularProgress size={20} color="inherit" /> : 'Sign In'}
            </Button>
          )}
        </DialogActions>
      </Dialog>
    </Box>
  );
}
