import React, { useState } from 'react';
import { Navigate, useNavigate } from 'react-router-dom';
import { 
  Box, 
  Card, 
  CardContent, 
  Typography, 
  TextField, 
  Button, 
  Alert,
  CircularProgress
} from '@mui/material';
import LockOutlinedIcon from '@mui/icons-material/LockOutlined';
import { api } from '../services/api';
import { useAuth } from '../contexts/AuthContext';

export function LoginPage() {
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  
  const { login, authenticated } = useAuth();
  const navigate = useNavigate();

  if (authenticated) {
    return <Navigate to="/dashboard" replace />;
  }

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!username.trim() || !password.trim()) {
      setError('Please enter both username and password.');
      return;
    }
    
    setLoading(true);
    setError(null);
    
    try {
      await api.loginAdmin(username.trim(), password.trim());
      login();
      navigate('/dashboard', { replace: true });
    } catch (err: any) {
      if (err.response?.status === 429) {
        setError('Too many login attempts. Please try again later.');
      } else if (err.response?.status === 401) {
        setError('Incorrect username or password.');
      } else {
        setError('An error occurred during login. Please ensure the backend is running.');
      }
    } finally {
      setLoading(false);
    }
  };

  return (
    <Box 
      sx={{ 
        height: '100vh', 
        display: 'flex', 
        alignItems: 'center', 
        justifyContent: 'center',
        bgcolor: '#f8fafc'
      }}
    >
      <Card sx={{ maxWidth: 400, width: '100%', mx: 2, boxShadow: '0 4px 6px -1px rgb(0 0 0 / 0.1), 0 2px 4px -2px rgb(0 0 0 / 0.1)' }}>
        <CardContent sx={{ p: 4 }}>
          <Box sx={{ display: 'flex', flexDirection: 'column', alignItems: 'center', mb: 3 }}>
            <Box sx={{ 
              bgcolor: '#e0e7ff', 
              color: '#4f46e5', 
              p: 1.5, 
              borderRadius: '50%',
              mb: 2
            }}>
              <LockOutlinedIcon fontSize="large" />
            </Box>
            <Typography variant="h5" sx={{ fontWeight: 600, color: "#1e293b" }}>
              NeoAlgo Terminal
            </Typography>
            <Typography variant="body2" color="#64748b" sx={{ mt: 1 }}>
              Secure administrative access
            </Typography>
          </Box>

          {error && (
            <Alert severity="error" sx={{ mb: 3 }}>
              {error}
            </Alert>
          )}

          <form onSubmit={handleSubmit}>
            <TextField
              fullWidth
              label="Username"
              variant="outlined"
              margin="normal"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              disabled={loading}
              autoComplete="username"
            />
            <TextField
              fullWidth
              label="Password"
              type="password"
              variant="outlined"
              margin="normal"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              disabled={loading}
              autoComplete="current-password"
            />
            <Button
              fullWidth
              variant="contained"
              color="primary"
              size="large"
              type="submit"
              disabled={loading}
              sx={{ 
                mt: 3, 
                mb: 2,
                py: 1.2,
                textTransform: 'none',
                fontWeight: 600,
                bgcolor: '#0f172a',
                '&:hover': {
                  bgcolor: '#1e293b'
                }
              }}
            >
              {loading ? <CircularProgress size={24} color="inherit" /> : 'Sign In'}
            </Button>
          </form>
        </CardContent>
      </Card>
    </Box>
  );
}
