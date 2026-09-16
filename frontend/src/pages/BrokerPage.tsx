import { Box, Typography, Card, CardContent, CardActions, Button, Chip, Avatar } from '@mui/material';
import Grid from '@mui/material/Grid';
import type { BrokerStatus } from '../types';
import VerifiedUserIcon from '@mui/icons-material/VerifiedUser';

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
  return (
    <Box sx={{ animation: 'fadeIn 0.3s' }}>
      <Typography variant="h5" sx={{ fontWeight: 700, mb: 3 }}>Broker Setup</Typography>
      
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
                    </Box>
                  )}
                </CardContent>
                <CardActions sx={{ justifyContent: 'center', pb: 3 }}>
                  <Button 
                    variant={isConnected ? "outlined" : "contained"} 
                    color={isConnected ? "error" : "primary"}
                    disabled={!broker.supported}
                    sx={{ borderRadius: 6, px: 4, textTransform: 'none', fontWeight: 600 }}
                  >
                    {isConnected ? "Disconnect" : "Connect"}
                  </Button>
                </CardActions>
              </Card>
            </Grid>
          );
        })}
      </Grid>
    </Box>
  );
}
