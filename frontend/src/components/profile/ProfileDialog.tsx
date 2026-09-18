import React, { useState, useEffect, useRef } from 'react';
import {
  Dialog,
  DialogTitle,
  DialogContent,
  DialogActions,
  Button,
  TextField,
  Box,
  Avatar,
  Typography,
  IconButton,
  CircularProgress,
  Alert,
  Divider,
  InputAdornment
} from '@mui/material';
import { Close as CloseIcon, CloudUpload as CloudUploadIcon, Delete as DeleteIcon, Visibility, VisibilityOff } from '@mui/icons-material';
import { useAuth } from '../../contexts/AuthContext';
import { api } from '../../services/api';
import { useNavigate } from 'react-router-dom';

interface ProfileDialogProps {
  open: boolean;
  onClose: () => void;
}

export default function ProfileDialog({ open, onClose }: ProfileDialogProps) {
  const { profile, refreshProfile } = useAuth();
  
  const [displayName, setDisplayName] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [successMessage, setSuccessMessage] = useState<string | null>(null);
  
  // Password state
  const [currentPassword, setCurrentPassword] = useState('');
  const [newPassword, setNewPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [showCurrentPassword, setShowCurrentPassword] = useState(false);
  const [showNewPassword, setShowNewPassword] = useState(false);
  const [showConfirmPassword, setShowConfirmPassword] = useState(false);
  
  const navigate = useNavigate();
  const fileInputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (open && profile) {
      setDisplayName(profile.display_name || '');
      setError(null);
      setSuccessMessage(null);
      setCurrentPassword('');
      setNewPassword('');
      setConfirmPassword('');
      setShowCurrentPassword(false);
      setShowNewPassword(false);
      setShowConfirmPassword(false);
    }
  }, [open, profile]);

  const handleSaveName = async () => {
    if (!displayName.trim()) {
      setError('Display name cannot be empty');
      return;
    }
    
    setLoading(true);
    setError(null);
    setSuccessMessage(null);
    
    try {
      await api.updateProfile(displayName);
      await refreshProfile();
      setSuccessMessage('Profile updated successfully');
      setTimeout(() => onClose(), 1500);
    } catch (err: any) {
      setError(err.message || 'Failed to update profile');
    } finally {
      setLoading(false);
    }
  };

  const handleFileChange = async (event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    if (!file) return;

    setLoading(true);
    setError(null);
    setSuccessMessage(null);

    try {
      await api.uploadAvatar(file);
      await refreshProfile();
      setSuccessMessage('Avatar uploaded successfully');
    } catch (err: any) {
      setError(err.message || 'Failed to upload avatar');
    } finally {
      setLoading(false);
      if (fileInputRef.current) {
        fileInputRef.current.value = '';
      }
    }
  };

  const handleRemoveAvatar = async () => {
    setLoading(true);
    setError(null);
    setSuccessMessage(null);

    try {
      await api.removeAvatar();
      await refreshProfile();
      setSuccessMessage('Avatar removed successfully');
    } catch (err: any) {
      setError(err.message || 'Failed to remove avatar');
    } finally {
      setLoading(false);
    }
  };

  const handleChangePassword = async () => {
    setError(null);
    setSuccessMessage(null);

    if (newPassword.length < 12) {
      setError('New password must be at least 12 characters.');
      return;
    }
    if (newPassword === currentPassword) {
      setError('New password cannot be identical to the current password.');
      return;
    }
    if (newPassword !== confirmPassword) {
      setError('Confirm password does not match new password.');
      return;
    }

    setLoading(true);
    try {
      await api.changePassword({
        current_password: currentPassword,
        new_password: newPassword
      });
      setSuccessMessage('Password changed successfully. Please sign in again.');
      setCurrentPassword('');
      setNewPassword('');
      setConfirmPassword('');
      
      // On success, redirect to login page because session is invalidated
      setTimeout(() => {
        onClose();
        navigate('/login');
        window.location.reload(); 
      }, 2000);
    } catch (err: any) {
      setError(err.message || 'Failed to change password');
    } finally {
      setLoading(false);
    }
  };

  // Build the safe avatar URL with timestamp to prevent caching
  const avatarUrl = profile?.avatar_url 
    ? `${profile.avatar_url}?t=${new Date().getTime()}`
    : undefined;

  return (
    <Dialog open={open} onClose={loading ? undefined : onClose} maxWidth="sm" fullWidth>
      <DialogTitle sx={{ m: 0, p: 2, display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <Typography variant="h6" component="div">
          Account Settings
        </Typography>
        <IconButton
          aria-label="close"
          onClick={onClose}
         disabled={loading}
          sx={{ color: (theme) => theme.palette.grey[500] }}
        >
          <CloseIcon />
        </IconButton>
      </DialogTitle>
      
      <DialogContent dividers sx={{ display: 'flex', flexDirection: 'column', gap: 3 }}>
        {error && <Alert severity="error">{error}</Alert>}
        {successMessage && <Alert severity="success">{successMessage}</Alert>}
        
        <Box sx={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 2 }}>
          <Avatar 
            src={avatarUrl} 
            sx={{ width: 100, height: 100, fontSize: '3rem' }}
          >
            {(displayName || 'A').charAt(0).toUpperCase()}
          </Avatar>
          
          <Box sx={{ display: 'flex', gap: 1 }}>
            <input
              type="file"
              accept="image/jpeg, image/png, image/webp"
              style={{ display: 'none' }}
              ref={fileInputRef}
              onChange={handleFileChange}
            />
            <Button 
              variant="outlined" 
              startIcon={loading ? <CircularProgress size={20} /> : <CloudUploadIcon />}
              onClick={() => fileInputRef.current?.click()}
              disabled={loading}
            >
              Change Photo
            </Button>
            
            {profile?.avatar_url && (
              <Button 
                variant="outlined" 
                color="error"
                startIcon={<DeleteIcon />}
                onClick={handleRemoveAvatar}
                disabled={loading}
              >
                Remove
              </Button>
            )}
          </Box>
          <Typography variant="caption" color="text.secondary">
            Allowed: JPG, PNG, WEBP. Max size: 5MB.
          </Typography>
        </Box>

        <Box sx={{ display: 'flex', flexDirection: 'column', gap: 2, mt: 2 }}>
          <TextField
            label="Login Username"
            value={profile?.username || 'admin'}
            disabled
            fullWidth
            helperText="This is a single-user system. The username cannot be changed."
          />
          <TextField
            label="Display Name"
            value={displayName}
            onChange={(e) => setDisplayName(e.target.value)}
            disabled={loading}
            fullWidth
            required
            autoFocus
          />
          <Button onClick={handleSaveName} disabled={loading || !displayName.trim()} variant="contained" sx={{ mt: 1 }}>
            Save Changes
          </Button>
        </Box>

        <Divider />
        
        <Box sx={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
          <Typography variant="h6">Security</Typography>
          <TextField
            label="Current Password"
            type={showCurrentPassword ? 'text' : 'password'}
            value={currentPassword}
            onChange={(e) => setCurrentPassword(e.target.value)}
            disabled={loading}
            fullWidth
            required
            variant="outlined"
            slotProps={{
              input: {
                endAdornment: (
                  <InputAdornment position="end">
                    <IconButton
                      aria-label="toggle current password visibility"
                      onClick={() => setShowCurrentPassword(!showCurrentPassword)}
                      edge="end"
                    >
                      {showCurrentPassword ? <VisibilityOff /> : <Visibility />}
                    </IconButton>
                  </InputAdornment>
                )
              }
            }}
          />
          <TextField
            label="New Password"
            type={showNewPassword ? 'text' : 'password'}
            value={newPassword}
            onChange={(e) => setNewPassword(e.target.value)}
            disabled={loading}
            fullWidth
            required
            variant="outlined"
            helperText="Password must contain at least 12 characters."
            slotProps={{
              input: {
                endAdornment: (
                  <InputAdornment position="end">
                    <IconButton
                      aria-label="toggle new password visibility"
                      onClick={() => setShowNewPassword(!showNewPassword)}
                      edge="end"
                    >
                      {showNewPassword ? <VisibilityOff /> : <Visibility />}
                    </IconButton>
                  </InputAdornment>
                )
              }
            }}
          />
          <TextField
            label="Confirm New Password"
            type={showConfirmPassword ? 'text' : 'password'}
            value={confirmPassword}
            onChange={(e) => setConfirmPassword(e.target.value)}
            disabled={loading}
            fullWidth
            required
            variant="outlined"
            slotProps={{
              input: {
                endAdornment: (
                  <InputAdornment position="end">
                    <IconButton
                      aria-label="toggle confirm password visibility"
                      onClick={() => setShowConfirmPassword(!showConfirmPassword)}
                      edge="end"
                    >
                      {showConfirmPassword ? <VisibilityOff /> : <Visibility />}
                    </IconButton>
                  </InputAdornment>
                )
              }
            }}
          />
          <Button 
            onClick={handleChangePassword} 
            disabled={loading || !currentPassword || !newPassword || !confirmPassword} 
            variant="contained" 
            color="secondary"
            sx={{ mt: 1 }}
          >
            {loading ? 'Changing Password...' : 'Change Password'}
          </Button>
        </Box>
      </DialogContent>
      
      <DialogActions sx={{ p: 2 }}>
        <Button onClick={onClose} disabled={loading} color="inherit">
          Close
        </Button>
      </DialogActions>
    </Dialog>
  );
}
