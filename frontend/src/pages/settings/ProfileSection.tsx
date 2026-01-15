/**
 * Seção de perfil dentro da página de configurações
 */

import React, { useEffect, useMemo, useState } from 'react';
import {
  Box,
  Button,
  Card,
  CardContent,
  CircularProgress,
  Divider,
  InputAdornment,
  ListItemIcon,
  Stack,
  TextField,
  Typography,
  Chip,
} from '@mui/material';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import PersonOutlineIcon from '@mui/icons-material/PersonOutline';
import { useToastContext } from '../../contexts/ToastContext';
import {
  getProfile,
  updateProfile,
  ProfileUpdatePayload,
  ProfileUpdateResponse,
} from '../../services/settingsService';
import useDebouncedValue from '../../hooks/useDebouncedValue';

interface ProfileFormState {
  name: string;
  email: string;
  phone_number: string;
}

interface ProfileFormErrors {
  name?: string;
  email?: string;
  phone_number?: string;
}

const emptyFormState: ProfileFormState = {
  name: '',
  email: '',
  phone_number: '',
};

const phoneRegex = /^\+?\d{10,15}$/;
const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

/**
 * Valida o nome informado para evitar atualizações incompletas
 */
const getNameError = (value: string): string | undefined => {
  if (!value.trim()) {
    return 'Informe o nome completo.';
  }
  return undefined;
};

/**
 * Seção de perfil
 * Permite ao usuário atualizar dados básicos e observar status de verificação
 */
const ProfileSection: React.FC = () => {
  const queryClient = useQueryClient();
  const { showToast } = useToastContext();
  const { data, isLoading } = useQuery({ queryKey: ['settings-profile'], queryFn: getProfile });
  const [formState, setFormState] = useState<ProfileFormState>(emptyFormState);
  const [errors, setErrors] = useState<ProfileFormErrors>({});
  const hasInitializedRef = React.useRef(false);
  const { debouncedValue: debouncedName, isDebouncing: isNameDebouncing } = useDebouncedValue(formState.name, 800);

  // Centraliza atualização local após mudanças no perfil para manter UI consistente.
  const handleProfileSuccess = (response: ProfileUpdateResponse, message: string) => {
    queryClient.setQueryData(['settings-profile'], response.profile);
    setFormState({
      name: response.profile.name,
      email: response.profile.email,
      phone_number: response.profile.phone_number ?? '',
    });
    setErrors({});
    showToast({
      message,
      severity: 'success',
    });
    if (response.email_verification_required) {
      showToast({
        message: 'Enviamos um novo email de verificação para o endereço atualizado.',
        severity: 'warning',
      });
    }
    if (response.phone_verification_required) {
      showToast({
        message: 'Enviamos um novo OTP para confirmar o telefone atualizado.',
        severity: 'warning',
      });
    }
  };

  const nameMutation = useMutation({
    mutationFn: (payload: ProfileUpdatePayload) => updateProfile(payload),
    onSuccess: (response: ProfileUpdateResponse) => {
      handleProfileSuccess(response, 'Nome atualizado com sucesso.');
    },
    onError: () => {
      showToast({
        message: 'Não foi possível atualizar o nome. Tente novamente.',
        severity: 'error',
      });
    },
  });

  const contactMutation = useMutation({
    mutationFn: (payload: ProfileUpdatePayload) => updateProfile(payload),
    onSuccess: (response: ProfileUpdateResponse) => {
      handleProfileSuccess(response, 'Dados de contato atualizados com sucesso.');
    },
    onError: () => {
      showToast({
        message: 'Não foi possível atualizar o perfil. Tente novamente.',
        severity: 'error',
      });
    },
  });

  useEffect(() => {
    if (!data) {
      return;
    }
    // Evita sincronizações redundantes que podem causar renderizações em cascata
    setFormState((prev) => {
      const nextState = {
        name: data.name,
        email: data.email,
        phone_number: data.phone_number ?? '',
      };
      const isSame =
        prev.name === nextState.name &&
        prev.email === nextState.email &&
        prev.phone_number === nextState.phone_number;
      if (isSame && hasInitializedRef.current) {
        return prev;
      }
      hasInitializedRef.current = true;
      return nextState;
    });
    setErrors((prev) => (Object.keys(prev).length > 0 ? {} : prev));
  }, [data]);

  useEffect(() => {
    if (!data || !hasInitializedRef.current) {
      return;
    }
    const trimmedName = debouncedName.trim();
    if (!trimmedName || trimmedName === data.name || getNameError(trimmedName)) {
      return;
    }
    // Usa autosave com debounce para evitar mutações em cada tecla pressionada.
    nameMutation.mutate({ name: trimmedName });
  }, [data, debouncedName, nameMutation]);

  const phoneStatus = useMemo(() => {
    if (!data?.phone_number) {
      return { label: 'Telefone não informado', color: 'default' as const };
    }
    if (data.phone_number_verified) {
      return { label: 'Telefone verificado', color: 'success' as const };
    }
    return { label: 'Telefone pendente', color: 'warning' as const };
  }, [data]);

  const handleFieldChange = (field: keyof ProfileFormState) => (event: React.ChangeEvent<HTMLInputElement>) => {
    const nextValue = event.target.value;
    setFormState((prev) => ({ ...prev, [field]: nextValue }));
    if (field === 'name') {
      const nameError = getNameError(nextValue);
      setErrors((prev) => ({ ...prev, name: nameError }));
      return;
    }
    setErrors((prev) => (prev[field] ? { ...prev, [field]: undefined } : prev));
  };

  const validateContact = (): ProfileFormErrors => {
    const nextErrors: ProfileFormErrors = {};
    if (!formState.email.trim() || !emailRegex.test(formState.email.trim())) {
      nextErrors.email = 'Informe um email válido.';
    }
    if (formState.phone_number.trim() && !phoneRegex.test(formState.phone_number.trim())) {
      nextErrors.phone_number = 'Informe um telefone válido com código do país.';
    }
    return nextErrors;
  };

  const handleContactSave = () => {
    const nextErrors = validateContact();
    setErrors(nextErrors);
    if (Object.keys(nextErrors).length > 0 || !data) {
      return;
    }

    const payload: ProfileUpdatePayload = {};
    if (data.email !== formState.email.trim()) {
      payload.email = formState.email.trim();
    }
    if ((data.phone_number ?? '') !== formState.phone_number.trim()) {
      payload.phone_number = formState.phone_number.trim() === '' ? null : formState.phone_number.trim();
    }
    if (Object.keys(payload).length === 0) {
      return;
    }
    contactMutation.mutate(payload);
  };

  if (isLoading) {
    return (
      <Box sx={{ display: 'flex', justifyContent: 'center', py: 6 }}>
        <CircularProgress />
      </Box>
    );
  }

  const hasContactChanges =
    data &&
    (data.email !== formState.email.trim() || (data.phone_number ?? '') !== formState.phone_number.trim());
  const isNameSaving = isNameDebouncing || nameMutation.isPending;

  return (
    <Stack spacing={3}>
      <Card elevation={2}>
        <CardContent>
          <Stack spacing={3}>
            <Box>
              <Stack direction="row" spacing={1.5} alignItems="center">
                <ListItemIcon sx={{ minWidth: 'auto', color: 'text.secondary' }}>
                  <PersonOutlineIcon fontSize="small" />
                </ListItemIcon>
                <Typography variant="h6">Perfil</Typography>
              </Stack>
            </Box>
            <Divider />
            <Stack spacing={2}>
              <TextField
                label="Nome Completo"
                value={formState.name}
                onChange={handleFieldChange('name')}
                error={!!errors.name}
                helperText={errors.name}
                InputProps={{
                  endAdornment: isNameSaving ? (
                    <InputAdornment position="end">
                      <CircularProgress size={16} />
                    </InputAdornment>
                  ) : undefined,
                }}
                fullWidth
              />
              <TextField
                label="Email"
                value={formState.email}
                onChange={handleFieldChange('email')}
                error={!!errors.email}
                helperText={errors.email}
                fullWidth
              />
              <TextField
                label="Telefone"
                value={formState.phone_number}
                onChange={handleFieldChange('phone_number')}
                error={!!errors.phone_number}
                helperText={errors.phone_number ?? 'Opcional, formato internacional com código de país.'}
                fullWidth
              />
              <Box sx={{ display: 'flex', justifyContent: 'flex-end' }}>
                <Button
                  size="small"
                  variant="contained"
                  onClick={handleContactSave}
                  disabled={!hasContactChanges || contactMutation.isPending}
                >
                  {contactMutation.isPending ? 'Salvando...' : 'Salvar contato'}
                </Button>
              </Box>
            </Stack>
            <Stack direction={{ xs: 'column', sm: 'row' }} spacing={2} alignItems="center">
              <Chip
                color={data?.email_verified ? 'success' : 'warning'}
                label={data?.email_verified ? 'Email Verificado' : 'Email Pendente'}
              />
              <Chip
                color={phoneStatus.color}
                label={phoneStatus.label}
              />
            </Stack>
          </Stack>
        </CardContent>
      </Card>
    </Stack>
  );
};

export default ProfileSection;
