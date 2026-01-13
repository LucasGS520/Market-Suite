import React from 'react';
import { Box, Button, Paper, Slide, Stack, Typography } from '@mui/material';

interface SaveBarProps {
    open: boolean;
    isSaving?: boolean;
    onSave: () => void;
    onCancel: () => void;
    label?: string; 
}

/**
 * SaveBar
 * Componente visual que destaca alterações pendentes e oferece ações rapidas para salvar ou cancelar.
 */
const SaveBar: React.FC<SaveBarProps> = ({ open, isSaving = false, onSave, onCancel, label }) => {
  return (
    <Slide direction="up" in={open} mountOnEnter unmountOnExit>
      <Paper elevation={3} sx={{ position: 'sticky', bottom: 0, mt: 3, p: 2, zIndex: 1 }}>
        <Stack
          direction={{ xs: 'column', sm: 'row' }}
          spacing={2}
          alignItems={{ xs: 'flex-start', sm: 'center' }}
          justifyContent="space-between"
        >
          <Box>
            <Typography variant="subtitle1" fontWeight={600}>
              {label ?? 'Alterações pendentes'}
            </Typography>
            <Typography variant="body2" color="text.secondary">
              Revise as mudanças antes de salvar.
            </Typography>
          </Box>
          <Stack direction="row" spacing={2} alignItems="center">
            <Button variant="outlined" onClick={onCancel} disabled={isSaving}>
              Cancelar
            </Button>
            <Button variant="contained" onClick={onSave} disabled={isSaving}>
              {isSaving ? 'Salvando...' : 'Salvar'}
            </Button>
          </Stack>
        </Stack>
      </Paper>
    </Slide>
  );
};

export default SaveBar;
