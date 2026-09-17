import { createTheme } from '@mui/material/styles';

export const theme = createTheme({
  palette: {
    mode: 'light',
    primary: {
      main: '#2563EB',
      dark: '#1E3A8A',
    },
    success: {
      main: '#16A34A',
    },
    error: {
      main: '#DC2626',
    },
    warning: {
      main: '#D97706',
    },
    info: {
      main: '#0284C7',
    },
    background: {
      default: '#F5F7FA',
      paper: '#FFFFFF',
    },
    text: {
      primary: '#0F172A',
      secondary: '#64748B',
    },
    divider: '#E2E8F0',
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
    borderRadius: 8,
  },
  components: {
    MuiCssBaseline: {
      styleOverrides: `
        @import url('https://fonts.googleapis.com/css2?family=Poppins:wght@400;500;600;700;800&display=swap');
        body {
          background-color: #F5F7FA;
          color: #0F172A;
        }
      `,
    },
    MuiButton: {
      styleOverrides: {
        root: {
          borderRadius: 8,
          padding: '8px 20px',
          fontWeight: 600,
          boxShadow: 'none',
          '&:hover': {
            boxShadow: 'none',
          }
        },
      },
    },
    MuiCard: {
      styleOverrides: {
        root: {
          borderRadius: 8,
          border: '1px solid #E2E8F0',
          boxShadow: '0 1px 2px 0 rgba(0, 0, 0, 0.05)',
          backgroundImage: 'none',
          '&:hover': {
            boxShadow: '0 4px 6px -1px rgba(0, 0, 0, 0.05), 0 2px 4px -1px rgba(0, 0, 0, 0.03)',
          },
          transition: 'box-shadow 0.2s ease',
        },
      },
    },
    MuiPaper: {
      styleOverrides: {
        root: {
          backgroundImage: 'none',
        },
        rounded: {
          borderRadius: 8,
        },
        outlined: {
          borderColor: '#E2E8F0',
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
            color: '#fff',
            '& + .MuiSwitch-track': {
              opacity: 1,
              backgroundColor: '#2563EB',
            },
          },
        },
        thumb: {
          width: 24,
          height: 24,
          boxShadow: '0 2px 4px rgba(0,0,0,0.1)',
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
          borderRadius: 6,
        },
      },
    },
    MuiTextField: {
      styleOverrides: {
        root: {
          '& .MuiOutlinedInput-root': {
            borderRadius: 8,
            fontWeight: 500,
            '& fieldset': {
              borderColor: '#E2E8F0',
            },
          },
        },
      },
    },
    MuiTableCell: {
      styleOverrides: {
        head: {
          fontWeight: 600,
          fontSize: '0.75rem',
          textTransform: 'uppercase',
          letterSpacing: '0.05em',
          color: '#64748B',
          borderBottom: '1px solid #E2E8F0',
        },
        body: {
          fontSize: '0.85rem',
          color: '#0F172A',
          borderBottom: '1px solid #E2E8F0',
        },
      },
    },
    MuiLinearProgress: {
      styleOverrides: {
        root: {
          height: 8,
          borderRadius: 4,
          backgroundColor: '#E2E8F0',
        },
      },
    },
    MuiAppBar: {
      styleOverrides: {
        root: {
          backgroundColor: '#FFFFFF',
          color: '#0F172A',
          borderBottom: '1px solid #E2E8F0',
          boxShadow: 'none',
        },
      },
    },
    MuiDrawer: {
      styleOverrides: {
        paper: {
          backgroundColor: '#FFFFFF',
          borderRight: '1px solid #E2E8F0',
        },
      },
    },
  },
});
