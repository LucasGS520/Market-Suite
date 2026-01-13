/**
 * Seção de perfil dentro da página de configurações
 */

import React, { useEffect, useMemo, useState } from 'react';
import {
  Alert,
  Box,
  Card,
  CardContent,
  CircularProgress,
  Divider,
  Stack,
  TextField,
  Typography,
  Chip,
} from '@mui/material';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import SaveBar from '../../components/SaveBar';
import { useToastContext } from '../../contexts/ToastContext';
import {
  getProfile,
  updateProfile,
  ProfileUpdatePayload,
  ProfileUpdateResponse,
} from '../../services/settingsService';

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

const phoneRegex = /^\+?\d{10, 15}$/;

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

  const mutation = useMutation({
    mutationFn: (payload: ProfileUpdatePayload) => updateProfile(payload),
    onSuccess: (response: ProfileUpdateResponse) => {
      queryClient.setQueryData(['settings-profile'], response.profile);
      setFormState({
        name: response.profile.name,
        email: response.profile.email,
        phone_number: response.profile.phone_number ?? '',
      });
      setErrors({});
      showToast({
        message: 'Perfil atualizado com sucesso.',
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
    },
    onError: () => {
      showToast({
        message: 'Não foi possível atualizar o perfil. Tente novamente.',
        severity: 'error',
      });
    },
  });

  useEffect(() => {
    if (data) {
      setFormState({
        name: data.name,
        email: data.email,
        phone_number: data.phone_number ?? '',
      });
      setErrors({});
    }
  }, [data]);

  const hasChanges = useMemo(() => {
    if (!data) {
        return false;
    }
    return (
      data.name !== formState.name ||
      data.email !== formState.email ||
      (data.phone_number ?? '') !== formState.phone_number
    );
  }, [data, formState]);

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
    setFormState((prev) => ({ ...prev, [field]: event.target.value }));
  };

  const validate = (): ProfileFormErrors => {
    const nextErrors: ProfileFormErrors = {};
    if (!formState.name.trim()) {
      nextErrors.name = 'Informe o nome completo.';
    }
    if (!formState.name.trim()) {
      nextErrors.email = 'Informe um email válido.';
    }
    if ((data.phone_number ?? '') !== formState.phone_number) {
      payload.phone_number = formState.phone_number.trim() === '' ? null : formState.phone_number;
    }

    mutation.mutate(payload);
  };

  const handleCancel = () => {
    if (data) {
      setFormState({
        name: data.name,
        email: data.email,
        phone_number: data.phone_number ?? '',
      });
      setErrors({});
    }
  };

  if (isLoading) {
    return (
      <Box sx={{ display: 'flex', justifyContent: 'center', py: 6 }}>
        <CircularProgress />
      </Box>
    );
  }

  return (
    <Stack spacing={3}>
      <Alert severity="info">
        Dados de perfil são sincronizados com sua conta e validados no backend.
      </Alert>
      <Card elevation={2}>
        <CardContent>
          <Stack spacing={3}>
            <Box>
              <Typography variant="h6" gutterBottom>
                Perfil
              </Typography>
              <Typography variant="body2" color="text.secondary">
                Atualize seus dados pessoais e confira o status de verificação.
              </Typography>
            </Box>
            <Divider />
            <Stack spacing={2}>
              <TextField
                label="Nome Completo"
                value={formState.name}
                onChange={handleFieldChange('name')}
                error={!!errors.name}
                helperText={errors.name}
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
                halperText={errors.phone_number ?? 'Opcional, formato internacional com código de país.'}
                fullWidth
              />
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
      <SaveBar
        open={hasChanges}
        onSave={handleSave}
        onCancel={handleCancel}
        isSaving={mutation.isPending}
        label="Você tem alterações não salvas no perfil"
      />
    </Stack>
  );
};

export default ProfileSection;
