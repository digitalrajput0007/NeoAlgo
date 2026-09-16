import React, { useState } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import Box from "@mui/material/Box";
import Drawer from "@mui/material/Drawer";
import List from "@mui/material/List";
import ListItem from "@mui/material/ListItem";
import ListItemButton from "@mui/material/ListItemButton";
import ListItemIcon from "@mui/material/ListItemIcon";
import ListItemText from "@mui/material/ListItemText";
import Typography from "@mui/material/Typography";
import Avatar from "@mui/material/Avatar";
import IconButton from "@mui/material/IconButton";
import Tooltip from "@mui/material/Tooltip";
import Collapse from "@mui/material/Collapse";
import ShowChartIcon from "@mui/icons-material/ShowChart";
import BusinessCenterIcon from "@mui/icons-material/BusinessCenter";
import ReceiptIcon from "@mui/icons-material/Receipt";
import AutoStoriesIcon from "@mui/icons-material/AutoStories";
import GppMaybeIcon from "@mui/icons-material/GppMaybe";
import DnsIcon from "@mui/icons-material/Dns";
import AnalyticsIcon from "@mui/icons-material/Analytics";
import {
  Dashboard as DashboardIcon,
  Timeline as TimelineIcon,
  Settings as SettingsIcon,
  Security as SecurityIcon,
  AutoGraph as AutoGraphIcon,
  AccountBalanceWallet as WalletIcon,
  History as HistoryIcon,
  NotificationsActive as AlertsIcon,
  Speed as SpeedIcon,
  MenuOpen as MenuOpenIcon,
  ListAlt as ListAltIcon,
  SwapHoriz as SwapHorizIcon,
  VpnKey as VpnKeyIcon,
  Telegram as TelegramIcon,
  InsertChartOutlined as InsertChartOutlinedIcon,
  ExpandLess,
  ExpandMore,
  RadioButtonUnchecked as RadioButtonUncheckedIcon,
} from '@mui/icons-material';
import { useAuth } from '../../contexts/AuthContext';
import ProfileMenu from '../profile/ProfileMenu';

interface SidebarProps {
  mobileOpen: boolean;
  onDrawerToggle: () => void;
  drawerOpen: boolean;
}

const navItems = [
  { id: "dashboard", label: "Dashboard", icon: DashboardIcon },
  {
    id: "trading_group",
    label: "Trading",
    icon: ShowChartIcon,
    children: [
      { id: "trades", label: "Active Trades" },
      { id: "positions", label: "Positions" },
      { id: "orders", label: "Orders" },
      { id: "signals", label: "Signals" },
    ]
  },
  { id: "market", label: "Market Data", icon: TimelineIcon },
  {
    id: "analysis_group",
    label: "Analysis",
    icon: AnalyticsIcon,
    children: [
      { id: "journal", label: "Trade Journal" },
      { id: "analytics", label: "Analytics" },
    ]
  },
  {
    id: "settings_group",
    label: "Settings & Controls",
    icon: SettingsIcon,
    children: [
      { id: "risk", label: "Risk Management" },
      { id: "controls", label: "Trading Controls" },
      { id: "telegram", label: "Telegram Connection" },
      { id: "connections", label: "Broker Setup" },
    ]
  },
  {
    id: "system_group",
    label: "System",
    icon: DnsIcon,
    children: [
      { id: "system", label: "System Health" },
      { id: "audit", label: "Audit Logs" },
    ]
  }
];

const drawerWidth = 260;
const collapsedDrawerWidth = 72;

export function Sidebar({ mobileOpen, onDrawerToggle, drawerOpen }: SidebarProps) {
  const currentWidth = drawerOpen ? drawerWidth : collapsedDrawerWidth;
  const location = useLocation();
  const navigate = useNavigate();
  
  // Extract active tab from pathname, defaulting to dashboard
  const activeTab = location.pathname === '/' ? 'dashboard' : location.pathname.replace('/', '');

  // State for which collapsible menus are open. By default, let's open them if an active tab is inside them.

  const [openGroups, setOpenGroups] = useState<Record<string, boolean>>({
    trading_group: true,
    settings_group: true,
  });

  const toggleGroup = (groupId: string) => {
    // If the drawer is collapsed, expanding a group should ideally temporarily open the drawer or just expand
    // But typically in mini variants, it's disabled or opens a popover. Here we just open the group.
    setOpenGroups(prev => ({ ...prev, [groupId]: !prev[groupId] }));
  };

  const isTabActive = (item: any) => {
    if (item.children) {
      return item.children.some((child: any) => child.id === activeTab);
    }
    return activeTab === item.id;
  };

  const drawerContent = (
    <Box sx={{ display: 'flex', flexDirection: 'column', height: '100%', mt: 8 }}>
      <Box sx={{ overflow: 'auto', flex: 1, px: drawerOpen ? 2 : 1 }}>
        <List disablePadding>
        {navItems.map((item) => {
          const hasChildren = !!item.children;
          const isActive = activeTab === item.id || (hasChildren && isTabActive(item));
          const isGroupOpen = !!openGroups[item.id];

          return (
            <React.Fragment key={item.id}>
              <ListItem disablePadding sx={{ mb: 0.5 }}>
                <ListItemButton
                  selected={isActive && !hasChildren} // only color primary if it's an exact match without children
                  onClick={() => {
                    if (hasChildren) {
                      toggleGroup(item.id);
                    } else {
                      navigate(`/${item.id}`);
                      if (mobileOpen) onDrawerToggle();
                    }
                  }}
                  sx={{
                    borderRadius: 2,
                    justifyContent: drawerOpen ? 'initial' : 'center',
                    px: drawerOpen ? 2 : 1.5,
                    '&.Mui-selected': {
                      backgroundColor: 'primary.light',
                      color: 'primary.contrastText',
                      '& .MuiListItemIcon-root': {
                        color: 'primary.contrastText',
                      },
                      '&:hover': {
                        backgroundColor: 'primary.main',
                      },
                    },
                  }}
                  title={!drawerOpen ? item.label : ""}
                >
                  <ListItemIcon 
                    sx={{ 
                      minWidth: drawerOpen ? 40 : 'auto', 
                      mr: drawerOpen ? 0 : 'auto',
                      color: (isActive && !hasChildren) ? 'inherit' : (isActive ? 'primary.main' : 'text.secondary') 
                    }}
                  >
                    <item.icon fontSize="small" />
                  </ListItemIcon>
                  {drawerOpen && (
                    <ListItemText 
                      primary={<Typography sx={{ fontSize: '0.875rem', fontWeight: isActive ? 600 : 500, color: (isActive && hasChildren) ? 'primary.main' : 'inherit' }}>{item.label}</Typography>} 
                    />
                  )}
                  {hasChildren && drawerOpen && (
                    isGroupOpen ? <ExpandLess sx={{ fontSize: 18, color: 'text.secondary' }} /> : <ExpandMore sx={{ fontSize: 18, color: 'text.secondary' }} />
                  )}
                </ListItemButton>
              </ListItem>

              {hasChildren && drawerOpen && (
                <Collapse in={isGroupOpen} timeout="auto" unmountOnExit>
                  <List component="div" disablePadding sx={{ pl: 3, mb: 1 }}>
                    {item.children.map((child: any) => {
                      const isChildActive = activeTab === child.id;
                      return (
                        <ListItemButton
                          key={child.id}
                          selected={isChildActive}
                          onClick={() => {
                            navigate(`/${child.id}`);
                            if (mobileOpen) onDrawerToggle();
                          }}
                          sx={{
                            borderRadius: 2,
                            py: 0.5,
                            mb: 0.25,
                            '&.Mui-selected': {
                              backgroundColor: 'rgba(99, 102, 241, 0.08)', // very light primary
                              color: 'primary.main',
                              '&:hover': {
                                backgroundColor: 'rgba(99, 102, 241, 0.12)',
                              },
                            },
                          }}
                        >
                          <ListItemIcon sx={{ minWidth: 28, color: isChildActive ? 'primary.main' : 'text.disabled' }}>
                            <RadioButtonUncheckedIcon sx={{ fontSize: 8 }} />
                          </ListItemIcon>
                          <ListItemText 
                            primary={<Typography sx={{ fontSize: '0.825rem', fontWeight: isChildActive ? 600 : 400 }}>{child.label}</Typography>} 
                          />
                        </ListItemButton>
                      );
                    })}
                  </List>
                </Collapse>
              )}
            </React.Fragment>
          );
        })}
        </List>
      </Box>
      <Box sx={{ mt: 'auto', p: drawerOpen ? 1 : 0.5, borderTop: '1px solid', borderColor: 'divider' }}>
        <ProfileMenu isSidebarExpanded={drawerOpen} />
      </Box>
    </Box>
  );


  return (
    <Box
      component="nav"
      sx={{ width: { lg: currentWidth }, flexShrink: { lg: 0 }, transition: 'width 0.2s' }}
    >
      <Drawer
        variant="temporary"
        open={mobileOpen}
        onClose={onDrawerToggle}
        ModalProps={{
          keepMounted: true,
        }}
        sx={{
          display: { xs: 'block', lg: 'none' },
          '& .MuiDrawer-paper': { boxSizing: 'border-box', width: drawerWidth },
        }}
      >
        {drawerContent}
      </Drawer>
      <Drawer
        variant="permanent"
        sx={{
          display: { xs: 'none', lg: 'block' },
          '& .MuiDrawer-paper': { boxSizing: 'border-box', width: currentWidth, transition: 'width 0.2s' },
        }}
        open
      >
        {drawerContent}
      </Drawer>
    </Box>
  );
}
