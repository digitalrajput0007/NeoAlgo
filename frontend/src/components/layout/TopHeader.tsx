import AppBar from "@mui/material/AppBar";
import Toolbar from "@mui/material/Toolbar";
import Typography from "@mui/material/Typography";
import Box from "@mui/material/Box";
import Chip from "@mui/material/Chip";
import { keyframes } from "@mui/system";
import SecurityIcon from "@mui/icons-material/Security";
import CircleIcon from "@mui/icons-material/Circle";
import WarningAmberIcon from "@mui/icons-material/WarningAmber";
import Stack from "@mui/material/Stack";
import IconButton from "@mui/material/IconButton";
import MenuIcon from "@mui/icons-material/Menu";
import MenuOpenIcon from "@mui/icons-material/MenuOpen";
import { MarketOverviewData, MarketOverviewTicker } from "../../types";

interface TopHeaderProps {
  tradingMode: string;
  sfeedStatus: string;
  telegramStatus: string;
  newTradesPaused: boolean;
  marketOverview: MarketOverviewData | null;
  onDrawerToggle: () => void;
  onDesktopDrawerToggle: () => void;
  drawerOpen: boolean;
}

const pulse = keyframes`
  0% { opacity: 1; transform: scale(1); }
  50% { opacity: 0.4; transform: scale(0.85); }
  100% { opacity: 1; transform: scale(1); }
`;

const PulsingDot = ({ color }: { color: string }) => (
  <Box sx={{
    width: 10,
    height: 10,
    borderRadius: '50%',
    backgroundColor: color,
    animation: `${pulse} 1.5s infinite ease-in-out`,
    ml: 1 // MUI Chip default icon margin
  }} />
);

export function TopHeader({
  tradingMode,
  sfeedStatus,
  telegramStatus,
  newTradesPaused,
  marketOverview,
  onDrawerToggle,
  onDesktopDrawerToggle,
  drawerOpen
}: TopHeaderProps) {
  return (
    <AppBar position="sticky" color="inherit" elevation={1} sx={{ zIndex: (theme) => theme.zIndex.drawer + 1 }}>
      <Toolbar>
        {/* Mobile menu button */}
        <IconButton
          color="inherit"
          aria-label="open drawer"
          edge="start"
          onClick={onDrawerToggle}
          sx={{ mr: 2, display: { lg: 'none' } }}
        >
          <MenuIcon />
        </IconButton>
        
        {/* Desktop menu toggle */}
        <IconButton
          color="inherit"
          aria-label="toggle drawer"
          edge="start"
          onClick={onDesktopDrawerToggle}
          sx={{ mr: 2, display: { xs: 'none', lg: 'flex' } }}
        >
          {drawerOpen ? <MenuOpenIcon /> : <MenuIcon />}
        </IconButton>

        <Box sx={{ display: 'flex', flexCol: 1, flexDirection: 'column' }}>
          <Typography variant="h6" noWrap component="div" color="primary.main" sx={{ fontWeight: 800, lineHeight: 1 }}>
            NeoAlgo
          </Typography>
          <Typography variant="caption" color="text.secondary" sx={{ fontWeight: 600, letterSpacing: 1 }}>
            PROFESSIONAL TERMINAL
          </Typography>
        </Box>

        <Box sx={{ flexGrow: 1 }} />

        {/* Desktop Tickers & Market Status (Centered) */}
        <Stack direction="row" spacing={2} sx={{ alignItems: 'center', display: { xs: 'none', md: 'flex' } }}>
          {marketOverview?.tickers?.filter((t: MarketOverviewTicker) => ['NIFTY 50', 'BANK NIFTY'].includes(t.symbol)).map((ticker: MarketOverviewTicker) => (
            <Box key={ticker.symbol} sx={{ display: 'flex', flexDirection: 'column', alignItems: 'center', px: 2, borderRight: '1px solid', borderColor: 'divider' }}>
              <Typography variant="caption" color="text.secondary" sx={{ fontWeight: 'bold', lineHeight: 1 }}>{ticker.symbol}</Typography>
              <Typography variant="body2" sx={{ fontWeight: 'bold', lineHeight: 1.2, color: ticker.status === 'LIVE' ? 'text.primary' : 'warning.main' }}>
                {ticker.ltp !== null ? ticker.ltp.toFixed(2) : '-'}
              </Typography>
            </Box>
          ))}
          
          <Chip
            size="small"
            label={marketOverview?.market_status || 'UNKNOWN'}
            sx={{ 
              fontWeight: 'bold', 
              bgcolor: marketOverview?.market_status === 'OPEN' ? 'success.main' : 
                       marketOverview?.market_status === 'PRE-OPEN' ? 'warning.main' : 'error.main',
              color: 'white'
            }}
          />
        </Stack>

        <Box sx={{ flexGrow: 1 }} />

        <Stack direction="row" spacing={2} sx={{ alignItems: 'center' }}>
          {tradingMode === "PAPER" ? (
            <Chip
              icon={<SecurityIcon fontSize="small" />}
              label={
                <Box sx={{ display: 'flex', flexDirection: 'column', py: 0.5 }}>
                  <Typography variant="caption" sx={{ fontWeight: 'bold', lineHeight: 1 }}>PAPER TRADING</Typography>
                  <Typography sx={{ fontSize: '0.65rem', lineHeight: 1 }}>Live broker orders disabled</Typography>
                </Box>
              }
              color="warning"
              variant="outlined"
              sx={{ height: 'auto', p: 0.5, borderRadius: 2 }}
            />
          ) : (
            <Chip
              icon={<WarningAmberIcon fontSize="small" />}
              label={
                <Box sx={{ display: 'flex', flexDirection: 'column', py: 0.5 }}>
                  <Typography variant="caption" sx={{ fontWeight: 'bold', lineHeight: 1 }}>LIVE TRADING: KOTAK NEO</Typography>
                  <Typography sx={{ fontSize: '0.65rem', lineHeight: 1 }}>Real financial risk active</Typography>
                </Box>
              }
              color="error"
              variant="filled"
              sx={{ height: 'auto', p: 0.5, borderRadius: 2, bgcolor: 'error.main', color: 'white' }}
            />
          )}

          <Box sx={{ height: 24, borderLeft: '1px solid', borderColor: 'divider', display: { xs: 'none', md: 'block' } }} />

          <Chip
            size="small"
            icon={<PulsingDot color={sfeedStatus === 'RECEIVING_TICKS' ? '#4caf50' : '#f44336'} />}
            label="SFeed"
            color={sfeedStatus === 'RECEIVING_TICKS' ? "success" : "error"}
            variant="outlined"
            sx={{ display: { xs: 'none', md: 'flex' }, color: 'text.primary' }}
          />

          <Chip
            size="small"
            icon={<PulsingDot color={telegramStatus === 'RUNNING' ? '#4caf50' : (telegramStatus === 'WAITING_FOR_CHANNEL' ? '#ff9800' : '#f44336')} />}
            label="Telegram"
            color={
              telegramStatus === 'RUNNING' ? "success" : 
              (telegramStatus === 'WAITING_FOR_CHANNEL') ? "warning" : 
              "error"
            }
            variant="outlined"
            sx={{ display: { xs: 'none', md: 'flex' }, color: 'text.primary' }}
          />

          {newTradesPaused ? (
            <Chip
              size="small"
              icon={<PulsingDot color="#f44336" />}
              label="TRADES PAUSED"
              color="error"
              variant="outlined"
              sx={{ display: { xs: 'none', md: 'flex' }, color: 'text.primary' }}
            />
          ) : (
            <Chip
              size="small"
              icon={<PulsingDot color="#4caf50" />}
              label="TRADING ACTIVE"
              color="success"
              variant="outlined"
              sx={{ display: { xs: 'none', md: 'flex' }, color: 'text.primary' }}
            />
          )}
        </Stack>
      </Toolbar>
    </AppBar>
  );
}
