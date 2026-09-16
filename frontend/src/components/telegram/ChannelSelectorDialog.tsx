import { useState } from 'react';
import Dialog from '@mui/material/Dialog';
import DialogTitle from '@mui/material/DialogTitle';
import DialogContent from '@mui/material/DialogContent';
import DialogActions from '@mui/material/DialogActions';
import Button from '@mui/material/Button';
import TextField from '@mui/material/TextField';
import List from '@mui/material/List';
import ListItem from '@mui/material/ListItem';
import ListItemButton from '@mui/material/ListItemButton';
import ListItemIcon from '@mui/material/ListItemIcon';
import ListItemText from '@mui/material/ListItemText';
import Radio from '@mui/material/Radio';
import Box from '@mui/material/Box';
import Typography from '@mui/material/Typography';
import { TelegramChannelItem } from '@/types';

interface ChannelSelectorDialogProps {
  open: boolean;
  onClose: () => void;
  channels: TelegramChannelItem[];
  selectedChannelId: string | null;
  onSelectChannel: (channelId: string, channelName: string) => void;
  loading: boolean;
  onRefreshChannels: () => void;
}

export function ChannelSelectorDialog({
  open,
  onClose,
  channels,
  selectedChannelId,
  onSelectChannel,
  loading,
  onRefreshChannels
}: ChannelSelectorDialogProps) {
  const [searchTerm, setSearchTerm] = useState('');
  const [localSelection, setLocalSelection] = useState<string | null>(selectedChannelId);

  const filteredChannels = channels.filter(c => 
    c.channel_name.toLowerCase().includes(searchTerm.toLowerCase()) || 
    (c.username && c.username.toLowerCase().includes(searchTerm.toLowerCase()))
  );

  const handleConfirm = () => {
    if (localSelection) {
      const selected = channels.find(c => c.channel_id.toString() === localSelection);
      if (selected) {
        onSelectChannel(localSelection, selected.channel_name);
      }
    }
  };

  return (
    <Dialog open={open} onClose={onClose} maxWidth="sm" fullWidth>
      <DialogTitle>Choose Signal Channel</DialogTitle>
      <DialogContent dividers>
        <Box sx={{ mb: 2 }}>
          <TextField
            fullWidth
            size="small"
            placeholder="Search channels..."
            value={searchTerm}
            onChange={(e) => setSearchTerm(e.target.value)}
          />
        </Box>
        
        {loading ? (
          <Typography variant="body2" color="text.secondary" align="center" sx={{ py: 4 }}>
            Loading channels...
          </Typography>
        ) : (
          <List sx={{ width: '100%', bgcolor: 'background.paper', maxHeight: 300, overflow: 'auto' }}>
            {filteredChannels.length === 0 ? (
              <Typography variant="body2" color="text.secondary" align="center" sx={{ py: 2 }}>
                No channels found.
              </Typography>
            ) : (
              filteredChannels.map((channel) => {
                const isSelected = localSelection === channel.channel_id.toString();
                return (
                  <ListItem key={channel.channel_id} disablePadding sx={{ mb: 0.5, border: '1px solid', borderColor: isSelected ? 'primary.main' : 'divider', borderRadius: 1 }}>
                    <ListItemButton onClick={() => setLocalSelection(channel.channel_id.toString())}>
                      <ListItemIcon>
                        <Radio
                          edge="start"
                          checked={isSelected}
                          tabIndex={-1}
                          disableRipple
                        />
                      </ListItemIcon>
                      <ListItemText 
                        primary={channel.channel_name} 
                        secondary={channel.channel_type + (channel.username ? ` (@${channel.username})` : '')} 
                      />
                    </ListItemButton>
                  </ListItem>
                );
              })
            )}
          </List>
        )}
      </DialogContent>
      <DialogActions>
        <Button onClick={onRefreshChannels} disabled={loading} sx={{ mr: 'auto' }}>
          Refresh Channels
        </Button>
        <Button onClick={onClose} color="inherit">Cancel</Button>
        <Button onClick={handleConfirm} variant="contained" disabled={!localSelection || loading}>
          Select Channel
        </Button>
      </DialogActions>
    </Dialog>
  );
}
