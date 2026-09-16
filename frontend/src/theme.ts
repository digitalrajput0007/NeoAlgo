import { createTheme } from '@mui/material/styles';

export const theme = createTheme({
  palette: {
    mode: 'light',
    primary: {
      main: '#4338ca',
      light: '#6366f1',
      dark: '#312e81',
    },
    secondary: {
      main: '#ec4899',
      light: '#f472b6',
      dark: '#be185d',
    },
    success: {
      main: '#10b981',
      light: '#34d399',
      dark: '#047857',
    },
    error: {
      main: '#ef4444',
      light: '#f87171',
      dark: '#b91c1c',
    },
    warning: {
      main: '#f59e0b',
      light: '#fbbf24',
      dark: '#b45309',
    },
    info: {
      main: '#0ea5e9',
      light: '#38bdf8',
      dark: '#0369a1',
    },
    background: {
      default: '#f1f5f9',
      paper: '#ffffff',
    },
  },
  typography: {
    fontFamily: '"Poppins", "Inter", "Roboto", sans-serif',
    h4: { fontWeight: 700, fontSize: '2rem' },
    h5: { fontWeight: 700, fontSize: '1.6rem' },
    h6: { fontWeight: 700, fontSize: '1.2rem' },
    subtitle1: { fontWeight: 600, fontSize: '1rem' },
    subtitle2: { fontWeight: 600, fontSize: '0.9rem' },
    body1: { fontWeight: 500, fontSize: '0.95rem' },
    body2: { fontWeight: 500, fontSize: '0.85rem' },
    caption: { fontWeight: 500, fontSize: '0.78rem' },
    overline: { fontWeight: 700, fontSize: '0.72rem', letterSpacing: '0.08em' },
    button: { textTransform: 'none', fontWeight: 600, fontSize: '0.9rem' },
  },
  shape: {
    borderRadius: 10,
  },
  components: {
    MuiCssBaseline: {
      styleOverrides: `
        @import url('https://fonts.googleapis.com/css2?family=Poppins:wght@400;500;600;700;800&display=swap');
      `,
    },
    MuiButton: {
      styleOverrides: {
        root: {
          borderRadius: 10,
          padding: '8px 20px',
          fontWeight: 600,
          boxShadow: 'none',
        },
      },
      variants: [
        {
          props: { variant: 'contained', color: 'primary' },
          style: {
            background: 'linear-gradient(135deg, #4338ca 0%, #6366f1 100%)',
            '&:hover': {
              background: 'linear-gradient(135deg, #312e81 0%, #4338ca 100%)',
              boxShadow: '0 4px 12px rgba(67, 56, 202, 0.4)',
            },
          }
        },
        {
          props: { variant: 'contained', color: 'error' },
          style: {
            background: 'linear-gradient(135deg, #dc2626 0%, #ef4444 100%)',
            '&:hover': {
              background: 'linear-gradient(135deg, #b91c1c 0%, #dc2626 100%)',
              boxShadow: '0 4px 12px rgba(239, 68, 68, 0.4)',
            },
          }
        },
        {
          props: { variant: 'contained', color: 'success' },
          style: {
            background: 'linear-gradient(135deg, #047857 0%, #10b981 100%)',
            '&:hover': {
              background: 'linear-gradient(135deg, #065f46 0%, #047857 100%)',
              boxShadow: '0 4px 12px rgba(16, 185, 129, 0.4)',
            },
          }
        }
      ],
    },
    MuiCard: {
      styleOverrides: {
        root: {
          borderRadius: 14,
          border: '1px solid #e2e8f0',
          boxShadow: '0 1px 3px 0 rgb(0 0 0 / 0.08), 0 4px 16px -4px rgb(0 0 0 / 0.06)',
          '&:hover': {
            boxShadow: '0 4px 20px -2px rgb(0 0 0 / 0.12)',
          },
          transition: 'box-shadow 0.2s ease',
        },
      },
    },
    MuiPaper: {
      styleOverrides: {
        rounded: {
          borderRadius: 14,
        },
        outlined: {
          borderColor: '#e2e8f0',
        },
      },
    },
    MuiSwitch: {
      styleOverrides: {
        root: {
          width: 52,
          height: 30,
          padding: 0,
        },
        switchBase: {
          padding: 3,
          '&.Mui-checked': {
            transform: 'translateX(22px)',
            '& + .MuiSwitch-track': {
              opacity: 1,
            },
          },
        },
        thumb: {
          width: 24,
          height: 24,
          boxShadow: '0 2px 4px rgba(0,0,0,0.2)',
        },
        track: {
          borderRadius: 15,
          opacity: 1,
          backgroundColor: '#cbd5e1',
        },
      },
    },
    MuiChip: {
      styleOverrides: {
        root: {
          fontWeight: 600,
        },
      },
    },
    MuiTextField: {
      styleOverrides: {
        root: {
          '& .MuiOutlinedInput-root': {
            borderRadius: 10,
            fontWeight: 500,
          },
        },
      },
    },
    MuiTableCell: {
      styleOverrides: {
        head: {
          fontWeight: 700,
          fontSize: '0.8rem',
          textTransform: 'uppercase',
          letterSpacing: '0.04em',
          color: '#475569',
        },
        body: {
          fontSize: '0.85rem',
        },
      },
    },
    MuiLinearProgress: {
      styleOverrides: {
        root: {
          height: 8,
          borderRadius: 4,
        },
      },
    },
  },
});
