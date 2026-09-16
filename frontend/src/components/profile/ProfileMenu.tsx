import React, { useState } from 'react';
import { 
  Box, 
  Avatar, 
  Typography, 
  IconButton, 
  Menu, 
  MenuItem, 
  ListItemIcon, 
  ListItemText, 
  Divider 
} from '@mui/material';
import { 
  AccountCircle as AccountCircleIcon, 
  Logout as LogoutIcon,
  MoreVert as MoreVertIcon 
} from '@mui/icons-material';
import { useAuth } from '../../contexts/AuthContext';
import ProfileDialog from './ProfileDialog';

interface ProfileMenuProps {
  isSidebarExpanded?: boolean;
}

export default function ProfileMenu({ isSidebarExpanded = true }: ProfileMenuProps) {
  const { profile, logout } = useAuth();
  const [anchorEl, setAnchorEl] = useState<null | HTMLElement>(null);
  const [dialogOpen, setDialogOpen] = useState(false);

  const handleOpenMenu = (event: React.MouseEvent<HTMLElement>) => {
    setAnchorEl(event.currentTarget);
  };

  const handleCloseMenu = () => {
    setAnchorEl(null);
  };

  const handleOpenDialog = () => {
    handleCloseMenu();
    setDialogOpen(true);
  };

  const handleCloseDialog = () => {
    setDialogOpen(false);
  };

  const handleLogout = () => {
    handleCloseMenu();
    logout();
  };

  // Safe fallback if profile is not loaded yet
  const displayName = profile?.display_name || 'Admin User';
  const roleLabel = profile?.role_label || 'Administrator';
  const avatarUrl = profile?.avatar_url 
    ? `http://localhost:8000${profile.avatar_url}?t=${new Date().getTime()}` // Add timestamp to break cache
    : undefined;

  return (
    <>
      <Box 
        onClick={handleOpenMenu}
        sx={{ 
          display: 'flex', 
          alignItems: 'center', 
          gap: 2, 
          cursor: 'pointer',
          p: 1,
          borderRadius: 1,
          '&:hover': {
            bgcolor: 'action.hover'
          }
        }}
      >
        <Avatar src={avatarUrl} sx={{ width: 40, height: 40 }}>
          {displayName.charAt(0).toUpperCase()}
        </Avatar>
        
        {isSidebarExpanded && (
          <>
            <Box sx={{ flex: 1, minWidth: 0 }}>
              <Typography variant="body2" sx={{ fontWeight: 'bold', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
                {displayName}
              </Typography>
              <Typography variant="caption" color="text.secondary" sx={{ display: 'block', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
                {roleLabel}
              </Typography>
            </Box>
            <IconButton size="small" edge="end">
              <MoreVertIcon fontSize="small" />
            </IconButton>
          </>
        )}
      </Box>

      <Menu
        anchorEl={anchorEl}
        open={Boolean(anchorEl)}
        onClose={handleCloseMenu}
        transformOrigin={{ horizontal: 'left', vertical: 'bottom' }}
        anchorOrigin={{ horizontal: 'left', vertical: 'top' }}
        slotProps={{
          paper: {
            sx: {
              width: 200,
              mt: -1,
              ml: 2,
            }
          }
        }}
      >
        <MenuItem onClick={handleOpenDialog}>
          <ListItemIcon>
            <AccountCircleIcon fontSize="small" />
          </ListItemIcon>
          <ListItemText>Account Settings</ListItemText>
        </MenuItem>
        <Divider />
        <MenuItem onClick={handleLogout}>
          <ListItemIcon>
            <LogoutIcon fontSize="small" color="error" />
          </ListItemIcon>
          <ListItemText>
            <Typography color="error">Logout</Typography>
          </ListItemText>
        </MenuItem>
      </Menu>

      <ProfileDialog open={dialogOpen} onClose={handleCloseDialog} />
    </>
  );
}
