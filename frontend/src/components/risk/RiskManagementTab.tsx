import type { RiskConfig } from "@/types";
import Card from "@mui/material/Card";
import CardContent from "@mui/material/CardContent";
import CardHeader from "@mui/material/CardHeader";
import Box from "@mui/material/Box";
import Typography from "@mui/material/Typography";
import TextField from "@mui/material/TextField";
import FormControlLabel from "@mui/material/FormControlLabel";
import Switch from "@mui/material/Switch";
import Button from "@mui/material/Button";
import Alert from "@mui/material/Alert";
import Grid from "@mui/material/Grid";
import Accordion from "@mui/material/Accordion";
import AccordionSummary from "@mui/material/AccordionSummary";
import AccordionDetails from "@mui/material/AccordionDetails";
import SaveIcon from "@mui/icons-material/Save";
import WarningAmberIcon from "@mui/icons-material/WarningAmber";
import ExpandMoreIcon from "@mui/icons-material/ExpandMore";

interface RiskManagementTabProps {
  riskConfig: RiskConfig | null;
  onSaveRiskConfig: (e: React.FormEvent<HTMLFormElement>) => void;
  saving: boolean;
  message: { type: 'success' | 'error', text: string } | null;
}

const statusSwitchStyle = {
  transform: 'scale(0.75)',
  transformOrigin: 'left center',
  ml: 0.5,
  mr: -1,
  '& .MuiSwitch-switchBase.Mui-checked': {
    color: 'success.main',
    '& + .MuiSwitch-track': { backgroundColor: 'success.main', opacity: 0.5 },
  },
  '& .MuiSwitch-switchBase:not(.Mui-checked)': {
    color: 'error.main',
    '& + .MuiSwitch-track': { backgroundColor: 'error.main', opacity: 0.5 },
  }
};


export function RiskManagementTab({ riskConfig, onSaveRiskConfig, saving, message }: RiskManagementTabProps) {
  const config = riskConfig || {
    max_daily_loss: 5000,
    max_risk_per_trade: 1000,
    max_trades_per_day: 5,
    max_simultaneous_positions: 2,
    daily_loss_protection_enabled: true,
    max_trades_protection_enabled: true,
    max_positions_protection_enabled: true,
    is_algo_active: false,
    entry_timeout_minutes: 5,
    entry_tolerance: 0.5,
    partial_profit_enabled: false,
    partial_profit_trigger: 1000,
    partial_profit_percentage: 50,
    trailing_stop_enabled: false,
    trailing_activation_mode: 'profit',
    trailing_activation_profit: 500,
    trailing_distance: 200,
  } as RiskConfig;

  return (
    <Box sx={{ maxWidth: '100%', mx: 'auto', animation: 'fadeIn 0.3s' }}>
      <form onSubmit={onSaveRiskConfig}>
        <Card elevation={2}>
          <CardHeader
            avatar={<WarningAmberIcon color="warning" />}
            title="Risk Management Configuration"
            subheader="Configure safety guardrails and daily loss limits. These are enforced in real-time."
            sx={{ borderBottom: 1, borderColor: 'divider' }}
          />
          <CardContent sx={{ pt: 4, px: 3 }}>
            
            <Accordion defaultExpanded elevation={0} variant="outlined" sx={{ mb: 2 }}>
              <AccordionSummary expandIcon={<ExpandMoreIcon />}>
                <Typography variant="subtitle1" sx={{ fontWeight: 700 }}>Daily Trading Limits</Typography>
              </AccordionSummary>
              <AccordionDetails>
                <Grid container spacing={3}>
                  <Grid size={{ xs: 12, md: 6 }}>
                    <TextField
                      fullWidth
                      type="number"
                      slotProps={{ htmlInput: { step: "0.01" } }}
                      label="Max Daily Loss (₹)"
                      name="max_daily_loss"
                      defaultValue={config.max_daily_loss}
                      size="small"
                    />
                    <FormControlLabel
                      control={<Switch size="medium" defaultChecked={config.daily_loss_protection_enabled} name="daily_loss_protection_enabled" sx={statusSwitchStyle} />}
                      label={<Typography variant="body2" sx={{ fontWeight: 600 }}>Enable daily loss protection</Typography>}
                      sx={{ mt: 1 }}
                    />
                  </Grid>
                  <Grid size={{ xs: 12, md: 6 }}>
                    <TextField
                      fullWidth
                      type="number"
                      label="Max Trades Per Day"
                      name="max_trades_per_day"
                      defaultValue={config.max_trades_per_day}
                      size="small"
                    />
                    <FormControlLabel
                      control={<Switch size="medium" defaultChecked={config.max_trades_protection_enabled} name="max_trades_protection_enabled" sx={statusSwitchStyle} />}
                      label={<Typography variant="body2" sx={{ fontWeight: 600 }}>Enable max trades limit</Typography>}
                      sx={{ mt: 1 }}
                    />
                  </Grid>
                </Grid>
              </AccordionDetails>
            </Accordion>

            <Accordion defaultExpanded elevation={0} variant="outlined" sx={{ mb: 2 }}>
              <AccordionSummary expandIcon={<ExpandMoreIcon />}>
                <Typography variant="subtitle1" sx={{ fontWeight: 700 }}>Position & Risk Sizing</Typography>
              </AccordionSummary>
              <AccordionDetails>
                <Grid container spacing={3}>
                  <Grid size={{ xs: 12, md: 6 }}>
                    <TextField
                      fullWidth
                      type="number"
                      slotProps={{ htmlInput: { step: "0.01" } }}
                      label="Max Risk Per Trade (₹)"
                      name="max_risk_per_trade"
                      defaultValue={config.max_risk_per_trade}
                      size="small"
                    />
                  </Grid>
                  <Grid size={{ xs: 12, md: 6 }}>
                    <TextField
                      fullWidth
                      type="number"
                      label="Max Simultaneous Positions"
                      name="max_simultaneous_positions"
                      defaultValue={config.max_simultaneous_positions}
                      size="small"
                    />
                    <FormControlLabel
                      control={<Switch size="medium" defaultChecked={config.max_positions_protection_enabled} name="max_positions_protection_enabled" sx={statusSwitchStyle} />}
                      label={<Typography variant="body2" sx={{ fontWeight: 600 }}>Enable max positions limit</Typography>}
                      sx={{ mt: 1 }}
                    />
                  </Grid>
                </Grid>
              </AccordionDetails>
            </Accordion>

            <Accordion defaultExpanded elevation={0} variant="outlined" sx={{ mb: 4 }}>
              <AccordionSummary expandIcon={<ExpandMoreIcon />}>
                <Typography variant="subtitle1" sx={{ fontWeight: 700 }}>Execution & Tolerance</Typography>
              </AccordionSummary>
              <AccordionDetails>
                <Grid container spacing={3}>
                  <Grid size={{ xs: 12, md: 6 }}>
                    <TextField
                      fullWidth
                      type="number"
                      label="Signal Timeout (Minutes)"
                      name="entry_timeout_minutes"
                      defaultValue={config.entry_timeout_minutes}
                      size="small"
                      helperText="Wait time before discarding signal"
                    />
                  </Grid>
                  <Grid size={{ xs: 12, md: 6 }}>
                    <TextField
                      fullWidth
                      type="number"
                      slotProps={{ htmlInput: { step: "0.1" } }}
                      label="Entry Tolerance (%)"
                      name="entry_tolerance"
                      defaultValue={config.entry_tolerance}
                      size="small"
                      helperText="Slippage tolerance from signal price"
                    />
                  </Grid>
                </Grid>
              </AccordionDetails>
            </Accordion>

            <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', pt: 3, borderTop: 1, borderColor: 'divider' }}>
              <FormControlLabel
                control={<Switch size="medium" defaultChecked={config.is_algo_active} name="is_algo_active" sx={statusSwitchStyle} />}
                label={<Typography variant="subtitle1" sx={{ fontWeight: 700 }}>Algorithm Master Switch</Typography>}
              />
              <Button type="submit" variant="contained" disabled={saving} startIcon={<SaveIcon />} size="large">
                {saving ? 'Saving...' : 'Save Configuration'}
              </Button>
            </Box>

            {message && (
              <Alert severity={message.type === 'success' ? 'success' : 'error'} sx={{ mt: 2 }}>
                {message.text}
              </Alert>
            )}
          </CardContent>
        </Card>
      </form>
    </Box>
  );
}
