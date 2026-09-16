import React, { createContext, useContext, useState, useEffect, ReactNode } from 'react';
import { api } from '../services/api';

export interface ProfileData {
  display_name: string;
  username: string;
  role_label: string;
  avatar_url: string | null;
}

interface AuthContextType {
  authenticated: boolean;
  loading: boolean;
  profile: ProfileData | null;
  login: () => void;
  logout: () => void;
  refreshProfile: () => Promise<void>;
}

const AuthContext = createContext<AuthContextType | undefined>(undefined);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [authenticated, setAuthenticated] = useState<boolean>(false);
  const [loading, setLoading] = useState<boolean>(true);
  const [profile, setProfile] = useState<ProfileData | null>(null);

  const fetchProfile = async () => {
    try {
      const data = await api.getProfile();
      setProfile(data);
    } catch (err) {
      setProfile(null);
    }
  };

  const checkAuth = async () => {
    try {
      const status = await api.checkAuthStatus();
      setAuthenticated(status.authenticated);
      if (status.authenticated) {
        await fetchProfile();
      }
    } catch (err) {
      setAuthenticated(false);
      setProfile(null);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    checkAuth();
    
    // Listen for global logout events emitted by the API interceptor
    const handleGlobalLogout = () => {
      setAuthenticated(false);
      setProfile(null);
    };
    window.addEventListener('auth:logout', handleGlobalLogout);
    return () => window.removeEventListener('auth:logout', handleGlobalLogout);
  }, []);

  const login = async () => {
    setAuthenticated(true);
    await fetchProfile();
  };

  const logout = async () => {
    try {
      await api.logoutAdmin();
    } catch (e) {
      // Ignore errors on logout
    }
    setAuthenticated(false);
    setProfile(null);
  };

  return (
    <AuthContext.Provider value={{ authenticated, loading, profile, login, logout, refreshProfile: fetchProfile }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const context = useContext(AuthContext);
  if (context === undefined) {
    throw new Error('useAuth must be used within an AuthProvider');
  }
  return context;
}
