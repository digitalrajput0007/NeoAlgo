import Box from "@mui/material/Box";
import Typography from "@mui/material/Typography";
import Button from "@mui/material/Button";
import ErrorIcon from "@mui/icons-material/Error";

interface ErrorStateProps {
  message: string;
  onRetry?: () => void;
}

export function ErrorState({ message, onRetry }: ErrorStateProps) {
  return (
    <Box sx={{ display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', p: 4, textAlign: 'center', bgcolor: 'background.paper', border: 1, borderColor: 'error.light', borderRadius: 3 }}>
      <Box sx={{ width: 48, height: 48, borderRadius: '50%', bgcolor: 'error.50', display: 'flex', alignItems: 'center', justifyContent: 'center', mb: 2 }}>
        <ErrorIcon color="error" />
      </Box>
      <Typography variant="subtitle2" gutterBottom>Failed to load data</Typography>
      <Typography variant="caption" color="text.secondary" sx={{ mb: 2, maxWidth: 300 }}>{message}</Typography>
      {onRetry && (
        <Button variant="outlined" size="small" onClick={onRetry}>Retry</Button>
      )}
    </Box>
  );
}
