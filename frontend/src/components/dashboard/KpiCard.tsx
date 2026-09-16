import React from 'react';
import Card from '@mui/material/Card';
import Box from '@mui/material/Box';
import Typography from '@mui/material/Typography';
import Chip from '@mui/material/Chip';

interface KpiCardProps {
  title: string;
  value: string | number;
  subtitle?: string;
  icon?: React.ReactNode;
  statusText?: string;
  statusColor?: 'default' | 'primary' | 'secondary' | 'error' | 'info' | 'success' | 'warning';
}

export function KpiCard({ title, value, subtitle, icon, statusText, statusColor = 'default' }: KpiCardProps) {
  return (
    <Card sx={{ p: 2, display: 'flex', flexDirection: 'column', height: '100%' }}>
      <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', mb: 2 }}>
        <Typography variant="subtitle2" color="text.secondary" sx={{ textTransform: 'uppercase', letterSpacing: 0.5, fontWeight: 600 }}>
          {title}
        </Typography>
        {icon && (
          <Box sx={{ color: 'text.secondary', display: 'flex' }}>
            {icon}
          </Box>
        )}
      </Box>
      
      <Typography variant="h4" component="div" sx={{ mb: 1, fontWeight: 700 }}>
        {value}
      </Typography>
      
      <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', mt: 'auto' }}>
        <Typography variant="body2" color="text.secondary">
          {subtitle || ' '}
        </Typography>
        {statusText && (
          <Chip 
            label={statusText} 
            color={statusColor} 
            size="small" 
            variant="outlined" 
            sx={{ height: 20, fontSize: '0.7rem', fontWeight: 600 }}
          />
        )}
      </Box>
    </Card>
  );
}
