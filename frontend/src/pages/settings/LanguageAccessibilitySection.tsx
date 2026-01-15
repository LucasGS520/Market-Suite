/**
 * Seção de idioma e acessibilidade com preferências locais
 */

import React, { useEffect, useMemo, useState } from 'react';
import {
  Box,
  Card,
  CardContent,
  CircularProgress,
  Divider,
  FormControl,
  InputLabel,
  ListItemIcon,
  MenuItem,
  Select,
  Stack,
  Typography,
} from '@mui/material';
import type { SelectChangeEvent } from '@mui/material/Select';
import LanguageIcon from '@mui/icons-material/Language';
import { useToastContext } from '../../contexts/ToastContext';
import useDebouncedValue from '../../hooks/useDebouncedValue';

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

type SelectablePreferenceField = 'language' | 'theme';

// Comparação explícita para evitar serialização repetidas ao salvar preferências
const arePreferencesEqual = (a: LocalPreferences, b: LocalPreferences): boolean => {
  return a.language === b.language && a.theme === b.theme && a.reduce_motion === b.reduce_motion;
};

/**
 * Lê preferências salvas do localStorage durante a criação do estado.
 */
const loadStoredPreferences = (): LocalPreferences => {
  if (typeof window === 'undefined') {
    return defaultPreferences;
  }
  const stored = localStorage.getItem(STORAGE_KEY);
  if (!stored) {
    return defaultPreferences;
  }
  try {
    return JSON.parse(stored) as LocalPreferences;
  } catch {
    return defaultPreferences;
  }
};

/**
 * Seção de idioma e acessibilidade
 * Gerencia preferências visuais salvas apenas no navegador
 */
const LanguageAccessibilitySection: React.FC = () => {
  const { showToast } = useToastContext();
  const [savedPreferences, setSavedPreferences] = useState<LocalPreferences>(() => loadStoredPreferences());
  const [formState, setFormState] = useState<LocalPreferences>(() => loadStoredPreferences());
  const hasLoadedRef = React.useRef(false);
  const { debouncedValue: debouncedPreferences, isDebouncing } = useDebouncedValue(formState, 800);
  const isSaving = useMemo(
    () => !arePreferencesEqual(savedPreferences, formState),
    [formState, savedPreferences],
  );

  useEffect(() => {
    // Evita exibir toast no primeiro render, já que o estado inicial já reflete o armazenamento.
    hasLoadedRef.current = true;
  }, []);

  useEffect(() => {
    if (!hasLoadedRef.current) {
      return;
    }
    if (arePreferencesEqual(savedPreferences, debouncedPreferences)) {
      return;
    }
    localStorage.setItem(STORAGE_KEY, JSON.stringify(debouncedPreferences));
    const timeoutId = window.setTimeout(() => {
      setSavedPreferences(debouncedPreferences);
      showToast({
        message: 'Preferências visuais salvas neste navegador.',
        severity: 'success',
      });
    }, 0);
    return () => {
      clearTimeout(timeoutId);
    };
  }, [debouncedPreferences, savedPreferences, showToast]);

  const handleSelectChange = (field: SelectablePreferenceField) => (event: SelectChangeEvent<string>) => {
    setFormState((prev) => ({ ...prev, [field]: event.target.value }));
  };

  return (
    <Stack spacing={3}>
      <Card elevation={2}>
        <CardContent>
          <Stack spacing={3}>
            <Box>
              <Stack direction="row" spacing={1.5} alignItems="center">
                <ListItemIcon sx={{ minWidth: 'auto', color: 'text.secondary' }}>
                  <LanguageIcon fontSize="small" />
                </ListItemIcon>
                <Typography variant="h6">Idioma & Acessibilidade</Typography>
                {(isSaving || isDebouncing) && <CircularProgress size={16} />}
              </Stack>
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
    </Stack>
  );
};
              
export default LanguageAccessibilitySection;
