import { ReactNode, useState } from "react";
import { Sidebar } from "./Sidebar";
import { TopHeader } from "./TopHeader";
import Box from "@mui/material/Box";

interface AppShellProps {
  children: ReactNode;
  tradingMode: string;
  sfeedStatus: string;
  telegramStatus: string;
  newTradesPaused: boolean;
}

export function AppShell({
  children,
  tradingMode,
  sfeedStatus,
  telegramStatus,
  newTradesPaused,
}: AppShellProps) {
  const [mobileOpen, setMobileOpen] = useState(false);
  const [drawerOpen, setDrawerOpen] = useState(true);

  const handleDrawerToggle = () => {
    setMobileOpen(!mobileOpen);
  };

  const handleDesktopDrawerToggle = () => {
    setDrawerOpen(!drawerOpen);
  };

  return (
    <Box sx={{ display: 'flex', minHeight: '100vh', bgcolor: 'background.default' }}>
      <Sidebar 
        mobileOpen={mobileOpen}
        onDrawerToggle={handleDrawerToggle}
        drawerOpen={drawerOpen}
      />
      <Box sx={{ flexGrow: 1, display: 'flex', flexDirection: 'column', minWidth: 0 }}>
        <TopHeader
          tradingMode={tradingMode}
          sfeedStatus={sfeedStatus}
          telegramStatus={telegramStatus}
          newTradesPaused={newTradesPaused}
          onDrawerToggle={handleDrawerToggle}
          onDesktopDrawerToggle={handleDesktopDrawerToggle}
          drawerOpen={drawerOpen}
        />
        <Box component="main" sx={{ flexGrow: 1, p: 3, overflowX: 'hidden' }}>
          <Box sx={{ maxWidth: 'xl', mx: 'auto' }}>
            {children}
          </Box>
        </Box>
      </Box>
    </Box>
  );
}
