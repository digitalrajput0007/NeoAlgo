import Box from "@mui/material/Box";
import Typography from "@mui/material/Typography";
import FolderSearchIcon from "@mui/icons-material/FolderSpecial";
import { ReactNode } from "react";

interface EmptyStateProps {
  title: string;
  description: string;
  icon?: ReactNode;
}

export function EmptyState({ title, description, icon }: EmptyStateProps) {
  return (
    <Box 
      sx={{ 
        display: 'flex', 
        flexDirection: 'column', 
        alignItems: 'center', 
        justifyContent: 'center', 
        p: 6, 
        textAlign: 'center', 
        bgcolor: 'background.default',
        border: '1px dashed',
        borderColor: 'divider',
        borderRadius: 3
      }}
    >
      <Box sx={{ width: 48, height: 48, borderRadius: '50%', bgcolor: 'grey.100', display: 'flex', alignItems: 'center', justifyContent: 'center', mb: 2, color: 'text.secondary' }}>
        {icon || <FolderSearchIcon />}
      </Box>
      <Typography variant="subtitle2" color="text.primary" gutterBottom>
        {title}
      </Typography>
      <Typography variant="caption" color="text.secondary" sx={{ maxWidth: 300 }}>
        {description}
      </Typography>
    </Box>
  );
}
