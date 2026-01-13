/**
 * Menu lateral para navegação entre seções de configruações
 */

import React from 'react';
import { Box, Chip, List, ListItemButton, ListItemText, Typography } from '@mui/material';

export interface SettingsMenuItem {
  id: string;
  label: string;
  description: string;
  visualOnly?: boolean;
}

interface SettingsMenuProps {
  items: SettingsMenuItem[];
  activeId: string;
  onSelect: (id: string) => void;
}

/**
 * SettingsMenu
 * Exibe as seções disponiveis e destaca a opção ativa
 */
const SettingsMenu: React.FC<SettingsMenuProps> = ({ items, activeId, onSelect }) => {
  return (
    <Box
      sx={{
        backgroundColor: 'background.paper',
        borderRadius: 2,
        border: '1px solid',
        borderColor: 'divider',
        overflow: 'hidden',
      }}
    >
      <Box sx={{ p: 2, borderBottom: '1px solid', borderColor: 'divider' }}>
        <Typography variant="subtitle2" color="text.secondary">
            Seções
        </Typography>
      </Box>
      <List disablePadding>
        {items.map((item) => (
          <ListItemButton
            key={item.id}
            selected={item.id === activeId}
            onClick={() => onSelect(item.id)}
            sx={{ alignItems: 'flex-start' }}
          >
            <ListItemText
              primary={
                <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                  <Typography variant="subtitle1" fontWeight={600}>
                    {item.label}
                  </Typography>
                  {item.visualOnly && (
                    <Chip size="small" label="Visual" color="default" />
                  )}
                </Box>
              }
              secondary={
                <Typography variant="body2" color="text.secondary">
                  {item.description}
                </Typography>
              }
            />
          </ListItemButton>
        ))}
      </List>
    </Box> 
  );
};

export default SettingsMenu;
