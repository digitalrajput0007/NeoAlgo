import { ReactNode } from "react";
import Card from "@mui/material/Card";
import CardContent from "@mui/material/CardContent";
import Typography from "@mui/material/Typography";
import Box from "@mui/material/Box";

interface KpiCardProps {
  label: string;
  value: ReactNode;
  subtext?: ReactNode;
  icon?: ReactNode;
  trend?: 'positive' | 'negative' | 'neutral';
}

export function KpiCard({ label, value, subtext, icon, trend }: KpiCardProps) {
  let valueColor = "text.primary";
  let bgGradient = 'linear-gradient(135deg, #f8fafc 0%, #ffffff 100%)';

  if (trend === 'positive') {
    valueColor = "#047857";
    bgGradient = 'linear-gradient(135deg, #ecfdf5 0%, #d1fae5 100%)';
  }
  if (trend === 'negative') {
    valueColor = "#b91c1c";
    bgGradient = 'linear-gradient(135deg, #fef2f2 0%, #fecaca 100%)';
  }

  return (
    <Card sx={{
      background: bgGradient,
      border: '1px solid',
      borderColor: trend === 'positive' ? '#a7f3d0' : trend === 'negative' ? '#fca5a5' : '#e2e8f0',
      '&:hover': { boxShadow: '0 6px 24px -4px rgba(0,0,0,0.15)', transform: 'translateY(-2px)' },
      transition: 'all 0.2s ease',
    }}>
      <CardContent sx={{ p: 3, '&:last-child': { pb: 3 } }}>
        <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', mb: 1.5 }}>
          <Typography
            variant="overline"
            color="text.secondary"
            sx={{ fontWeight: 700, lineHeight: 1, fontSize: '0.75rem', letterSpacing: '0.08em' }}
          >
            {label}
          </Typography>
          {icon && (
            <Box sx={{
              color: trend === 'positive' ? 'success.main' : trend === 'negative' ? 'error.main' : 'text.disabled',
              display: 'flex',
              p: 0.8,
              borderRadius: 2,
              bgcolor: trend === 'positive' ? 'rgba(16,185,129,0.1)' : trend === 'negative' ? 'rgba(239,68,68,0.1)' : 'rgba(0,0,0,0.04)',
            }}>
              {icon}
            </Box>
          )}
        </Box>
        
        <Typography
          variant="h4"
          component="div"
          sx={{
            fontWeight: 800,
            color: valueColor,
            mb: 0.5,
            fontSize: { xs: '1.6rem', md: '2rem' },
            lineHeight: 1.2,
            fontFamily: '"Poppins", sans-serif',
          }}
        >
          {value}
        </Typography>
        
        {subtext && (
          <Typography variant="body2" color="text.secondary" sx={{ fontWeight: 500, mt: 0.5 }}>
            {subtext}
          </Typography>
        )}
      </CardContent>
    </Card>
  );
}
