import { Box, Typography, Card, CardContent, CardActions, Button, Chip, Avatar, CircularProgress, Divider, Switch, FormControlLabel, Dialog, DialogTitle, DialogContent, DialogActions, Checkbox, Alert } from '@mui/material';
import Grid from '@mui/material/Grid';
import { useEffect, useState } from 'react';
import type { BrokerStatus, BrokerFunds, TradingModeConfig } from '../types';
import VerifiedUserIcon from '@mui/icons-material/VerifiedUser';
import AccountBalanceWalletIcon from '@mui/icons-material/AccountBalanceWallet';
import { api } from '../services/api';

interface BrokerPageProps {
  status: BrokerStatus | null;
}

const BROKERS = [
  {
    id: 'kotak_neo',
    name: 'Kotak Neo',
    logo: 'K',
    logoUrl: 'https://www.kotakneo.com/assets/Kotak_Neo_Website_dark_mode.svg',
    color: '#ed1c24',
    supported: true
  },
  {
    id: 'kite',
    name: 'Zerodha Kite',
    logo: 'Z',
    color: '#eb5e28',
    supported: false
  },
  {
    id: 'dhan',
    name: 'Dhan',
    logo: 'D',
    color: '#4f46e5',
    supported: false
  },
  {
    id: 'fyers',
    name: 'Fyers',
    logo: 'F',
    color: '#0ea5e9',
    supported: false
  }
];

export function BrokerPage({ status }: BrokerPageProps) {
  const [funds, setFunds] = useState<BrokerFunds | null>(null);
  const [loadingFunds, setLoadingFunds] = useState(false);
  const [modeConfig, setModeConfig] = useState<TradingModeConfig | null>(null);
  const [loadingMode, setLoadingMode] = useState(false);
  const [confirmDialogOpen, setConfirmDialogOpen] = useState(false);
  const [confirmChecked, setConfirmChecked] = useState(false);
  
  const fetchMode = async () => {
    try {
      setLoadingMode(true);
      const config = await api.getTradingMode();
      setModeConfig(config);
    } catch (err) {
      console.error('Failed to fetch trading mode', err);
    } finally {
      setLoadingMode(false);
    }
  };

  const handleModeToggle = async () => {
    if (modeConfig?.mode === 'PAPER') {
      // Prompt confirmation to go live
      setConfirmChecked(false);
      setConfirmDialogOpen(true);
    } else {
      // Switch back to paper (no confirmation needed)
      try {
        setLoadingMode(true);
        const config = await api.setTradingMode('PAPER', false, true);
        setModeConfig(config);
      } catch (err) {
        console.error('Failed to set paper mode', err);
      } finally {
        setLoadingMode(false);
      }
    }
  };

  const handleConfirmLive = async () => {
    try {
      setLoadingMode(true);
      const config = await api.setTradingMode('LIVE', true, true);
      setModeConfig(config);
    } catch (err) {
      console.error('Failed to set live mode', err);
    } finally {
      setLoadingMode(false);
      setConfirmDialogOpen(false);
    }
  };
  
  const fetchFunds = async (refresh = false) => {
    try {
      setLoadingFunds(true);
      const res = await api.getBrokerAccountLimits(refresh);
      if (res) {
        setFunds(res);
      }
    } catch (err) {
      console.error('Failed to fetch broker funds', err);
    } finally {
      setLoadingFunds(false);
    }
  };

  useEffect(() => {
    if (status?.auth_status === 'CONNECTED') {
      fetchFunds();
    }
  }, [status]);

  useEffect(() => {
    fetchMode();
  }, []);

  return (
    <Box sx={{ animation: 'fadeIn 0.3s' }}>
      <Typography variant="h5" sx={{ fontWeight: 700, mb: 3 }}>Broker Setup & Funds</Typography>
      
      {/* Trading Mode Control */}
      <Card sx={{ mb: 4, border: 1, borderColor: modeConfig?.mode === 'LIVE' ? 'error.main' : 'divider' }}>
        <CardContent sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
          <Box>
            <Typography variant="h6" sx={{ fontWeight: 700, display: 'flex', alignItems: 'center', gap: 1 }}>
              Trading Mode
              {modeConfig?.mode === 'LIVE' ? (
                <Chip label="LIVE TRADING" color="error" size="small" sx={{ fontWeight: 700 }} />
              ) : (
                <Chip label="PAPER TRADING" color="success" size="small" sx={{ fontWeight: 700 }} />
              )}
            </Typography>
            <Typography variant="body2" color="text.secondary" sx={{ mt: 1 }}>
              {modeConfig?.mode === 'LIVE' 
                ? 'Warning: Real orders will be placed using actual funds.' 
                : 'Safe mode: Orders are simulated. No real money is used.'}
            </Typography>
          </Box>
          <Box sx={{ display: 'flex', alignItems: 'center', gap: 2 }}>
            {loadingMode && <CircularProgress size={24} />}
            <FormControlLabel
              control={
                <Switch 
                  checked={modeConfig?.mode === 'LIVE'} 
                  onChange={handleModeToggle}
                  disabled={loadingMode || !modeConfig}
                  color="error"
                />
              }
              label={modeConfig?.mode === 'LIVE' ? "Disable Live" : "Enable Live"}
            />
          </Box>
        </CardContent>
      </Card>

      <Typography variant="h6" sx={{ fontWeight: 700, mb: 2 }}>Broker Connections</Typography>
      <Grid container spacing={3}>
        {BROKERS.map((broker) => {
          // Force Kotak Neo as connected as requested by user
          const isConnected = broker.id === 'kotak_neo' ? true : false;
          
          return (
            <Grid size={{ xs: 12, sm: 6, md: 3 }} key={broker.id}>
              <Card sx={{ 
                height: '100%', 
                display: 'flex', 
                flexDirection: 'column',
                border: isConnected ? 2 : 1,
                borderColor: isConnected ? 'success.main' : 'divider',
                opacity: broker.supported ? 1 : 0.7,
                transition: 'transform 0.2s, box-shadow 0.2s',
                '&:hover': {
                  transform: broker.supported ? 'translateY(-4px)' : 'none',
                  boxShadow: broker.supported ? 4 : 1
                }
              }}>
                <CardContent sx={{ flexGrow: 1, display: 'flex', flexDirection: 'column', alignItems: 'center', textAlign: 'center' }}>
                  <Avatar 
                    sx={{ 
                      width: 72, 
                      height: 72, 
                      bgcolor: broker.color,
                      fontSize: '2.5rem',
                      fontWeight: 'bold',
                      mb: 2,
                      boxShadow: 2,
                      '& img': {
                        objectFit: 'contain',
                        width: '80%',
                        height: '80%'
                      }
                    }}
                  >
                    {broker.logoUrl ? (
                      <img src={broker.logoUrl} alt={`${broker.name} logo`} />
                    ) : (
                      broker.logo
                    )}
                  </Avatar>
                  <Typography variant="h6" sx={{ fontWeight: 700, mb: 1 }}>{broker.name}</Typography>
                  
                  {broker.supported ? (
                    isConnected ? (
                      <Chip icon={<VerifiedUserIcon />} label="Connected" color="success" size="small" sx={{ fontWeight: 600 }} />
                    ) : (
                      <Chip label="Disconnected" color="default" size="small" />
                    )
                  ) : (
                    <Chip label="Coming Soon" color="primary" variant="outlined" size="small" sx={{ fontWeight: 600 }} />
                  )}
                  
                  {isConnected && (
                    <Box sx={{ mt: 3, p: 1.5, bgcolor: 'background.default', borderRadius: 1, width: '100%', textAlign: 'left' }}>
                      <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mb: 0.5 }}>
                        <strong>Client Code:</strong> {status?.profile?.client_code || 'SBIE123'}
                      </Typography>
                      <Typography variant="caption" color="text.secondary" sx={{ display: 'block' }}>
                        <strong>Session:</strong> {status?.trading_session || 'ACTIVE'}
                      </Typography>
                      
                      <Divider sx={{ my: 1.5 }} />
                      
                      <Box sx={{ display: 'flex', alignItems: 'center', mb: 1 }}>
                        <AccountBalanceWalletIcon sx={{ fontSize: 16, mr: 0.5, color: 'primary.main' }} />
                        <Typography variant="subtitle2" sx={{ fontWeight: 600 }}>Available Margin</Typography>
                        {loadingFunds && <CircularProgress size={12} sx={{ ml: 1 }} />}
                      </Box>
                      
                      {funds ? (
                        <>
                          <Typography variant="h6" color={funds.available_margin !== null && funds.available_margin > 0 ? "success.main" : "error.main"} sx={{ fontWeight: 700 }}>
                            {funds.available_margin !== null ? `₹${funds.available_margin.toLocaleString('en-IN', { minimumFractionDigits: 2 })}` : 'N/A'}
                          </Typography>
                          <Typography variant="caption" color="text.secondary" sx={{ display: 'flex', justifyContent: 'space-between', mt: 0.5 }}>
                            <span>Used: {funds.used_margin !== null ? `₹${funds.used_margin.toLocaleString('en-IN', { minimumFractionDigits: 2 })}` : 'N/A'}</span>
                            <span>Cash: {funds.available_cash !== null ? `₹${funds.available_cash.toLocaleString('en-IN', { minimumFractionDigits: 2 })}` : 'N/A'}</span>
                          </Typography>
                          {funds.rms_pay_in !== null && (
                            <Typography variant="caption" color="text.secondary" sx={{ display: 'flex', justifyContent: 'space-between', mt: 0.5 }}>
                              <span>Pay-In: ₹{funds.rms_pay_in.toLocaleString('en-IN', { minimumFractionDigits: 2 })}</span>
                              <span>Collateral: {funds.collateral !== null ? `₹${funds.collateral.toLocaleString('en-IN', { minimumFractionDigits: 2 })}` : 'N/A'}</span>
                            </Typography>
                          )}
                        </>
                      ) : (
                        <Typography variant="body2" color="text.secondary">
                          {loadingFunds ? 'Loading funds...' : 'Funds data not available'}
                        </Typography>
                      )}
                    </Box>
                  )}
                </CardContent>
                <CardActions sx={{ justifyContent: 'space-between', pb: 3, px: 3 }}>
                  <Button 
                    variant={isConnected ? "outlined" : "contained"} 
                    color={isConnected ? "error" : "primary"}
                    disabled={!broker.supported}
                    sx={{ borderRadius: 6, px: 3, textTransform: 'none', fontWeight: 600 }}
                  >
                    {isConnected ? "Disconnect" : "Connect"}
                  </Button>
                  {isConnected && (
                    <Button 
                      variant="text" 
                      color="primary"
                      size="small"
                      onClick={() => fetchFunds(true)}
                      disabled={loadingFunds}
                      sx={{ textTransform: 'none' }}
                    >
                      Refresh Funds
                    </Button>
                  )}
                </CardActions>
              </Card>
            </Grid>
          );
        })}
      </Grid>

      {/* Confirmation Dialog */}
      <Dialog open={confirmDialogOpen} onClose={() => setConfirmDialogOpen(false)} maxWidth="sm" fullWidth>
        <DialogTitle sx={{ color: 'error.main', fontWeight: 700, display: 'flex', alignItems: 'center', gap: 1 }}>
          ⚠️ WARNING: ENABLE LIVE TRADING
        </DialogTitle>
        <DialogContent>
          <Alert severity="error" sx={{ mb: 3 }}>
            You are about to enable LIVE execution mode. Real orders will be placed using your broker account.
          </Alert>
          <Typography variant="body1" sx={{ mb: 2 }}>
            This action involves real financial risk. Please confirm that you understand the risks and wish to proceed.
          </Typography>
          <FormControlLabel
            control={
              <Checkbox 
                checked={confirmChecked}
                onChange={(e) => setConfirmChecked(e.target.checked)}
                color="error"
              />
            }
            label="I confirm that I want to enable LIVE trading and accept all associated financial risks."
          />
        </DialogContent>
        <DialogActions sx={{ p: 3, pt: 0 }}>
          <Button onClick={() => setConfirmDialogOpen(false)} color="inherit" variant="outlined">
            Cancel
          </Button>
          <Button 
            onClick={handleConfirmLive} 
            color="error" 
            variant="contained" 
            disabled={!confirmChecked || loadingMode}
          >
            {loadingMode ? <CircularProgress size={24} color="inherit" /> : 'Enable Live Trading'}
          </Button>
        </DialogActions>
      </Dialog>
    </Box>
  );
}
