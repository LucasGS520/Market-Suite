/**
 * Seção de idioma e acessibilidade com preferências locais
 */

import React, { useEffect, useMemo, useState } from 'react';
import {
  Alert,
  Box,
  Card,
  CardContent,
  Divider,
  FormControl,
  InputLabel,
  MenuItem,
  Select,
  Stack,
  Typography,
} from '@mui/material';
import type { SelectChangeEvent } from '@mui/material/Select';
import SaveBar from '../../components/settings/SaveBar';
import { useToastContext } from '../../contexts/ToastContext';

interface LocalPreferences {
    language: string;
    theme: string;
    reduce_motion: boolean;
}

const STORAGE_KEY = 'market-suite.settings.ui';

const defaultPreferences: LocalPreferences = {
    language: 'pt-BR',
    theme: 'light',
    reduce_motion: false,
};

/**
 * Seção de idioma e acessibilidade
 * Gerencia preferências visuais salvas apenas no navegador
 */
const LanguageAccessibilitySection: React.FC = () => {
  const { showToast } = useToastContext();
  const [savedPreferences, setSavedPreferences] = useState<LocalPreferences>(defaultPreferences);
  const [formState, setFormState] = useState<LocalPreferences>(defaultPreferences);

  useEffect(() => {
    const stored = localStorage.getItem(STORAGE_KEY);
    if (stored) {
      try {
        const parsed = JSON.parse(stored) as LocalPreferences;
        setSavedPreferences(parsed);
        setFormState(parsed);
      } catch {
        setSavedPreferences(defaultPreferences);
        setFormState(defaultPreferences);
      }
    }
  }, []);

  const hasChanges = useMemo(() => {
    return JSON.stringify(savedPreferences) !== JSON.stringify(formState);
  }, [savedPreferences, formState]);

  const handleSelectChange = (field: keyof LocalPreferences) => (event: SelectChangeEvent<string>) => {
    setFormState((prev) => ({...prev, [field]: event.target.value }));
  };

  const handleSave = () => {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(formState));
    setSavedPreferences(formState);
    showToast({
      message: 'Preferências visuais salvas neste navegador.',
      severity: 'success',
    });
  };

  const handleCancel = () => {
    setFormState(savedPreferences);
  };

  return (
    <Stack spacing={3}>
      <Alert severity="info">
        Preferências de idioma e acessibilidade são visuais e ficam salvas apenas neste navegador.
      </Alert>
      <Card elevation={2}>
        <CardContent>
          <Stack spacing={3}>
            <Box>
              <Typography variant="h6" gutterBottom>
                Idioma & Acessibilidade
              </Typography>
              <Typography variant="body2" color="text.secondary">
                Ajustes locais para personalizar experiência visual.
              </Typography>
            </Box>
            <Divider />
            <Stack spacing={2}>
              <FormControl fullWidth>
                <InputLabel id="language-label">Idioma</InputLabel>
                <Select
                  labelId="language-label"
                  label="Idioma"
                  value={formState.language}
                  onChange={handleSelectChange('language')}
                >
                  <MenuItem value="pt-BR">Português (Brasil)</MenuItem>
                  <MenuItem value="en-US">English (US)</MenuItem>
                  <MenuItem value="es-ES">Español (ES)</MenuItem>
                </Select>
              </FormControl>
              <FormControl fullWidth>
                <InputLabel id="theme-label">Tema</InputLabel>
                <Select
                  labelId="theme-label"
                  label="Tema"
                  value={formState.theme}
                  onChange={handleSelectChange('theme')}
                >
                  <MenuItem value="light">Claro</MenuItem>
                  <MenuItem value="dark">Escuro</MenuItem>
                </Select>
              </FormControl>
            </Stack>
          </Stack>
        </CardContent>
      </Card>
      <SaveBar
        open={hasChanges}
        onSave={handleSave}
        onCancel={handleCancel}
        label="Você tem ajustes visuais pendentes"
      />
    </Stack>
  );
};
              
export default LanguageAccessibilitySection;
