/**
 * Seção de notificações dentro da página de configurações
 */

import React, { useEffect, useMemo, useState } from 'react';
import {
  Alert,
  Box,
  Card,
  CardContent,
  CircularProgress,
  Divider,
  FormControlLabel,
  FormGroup,
  Stack,
  Switch,
  Typography,
} from '@mui/material';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import SaveBar from '../../components/SaveBar';
import { useToastContext } from '../../contexts/ToastContext';
import {
    getNotificationSettings,
    updateNotificationSettings,
    NotificationSettings,
} from '../../services/settingsService';

/**
 * Seção de notificações
 * Controla os canais de entrega habilitados para o usuário
 */
const NotificationsSection: React.FC = () => {
  const queryClient = useQueryClient();
  const { showToast } = useToastContext();
  const { data, isLoading } = useQuery({
    queryKey: ['settings-notifications'],
    queryFn: getNotificationSettings,
  });
  const [formState, setFormState] = useState<NotificationSettings | null>(null);

  const mutation = useMutation({
    mutationFn: (payload: NotificationSettings) => updateNotificationSettings(payload),
    onSuccess: (response) => {
      queryClient.setQueryData(['settings-notifications'], response);
      setFormState(response);
      showToast({
        message: 'Preferências de notificação atualizadas.',
        severity: 'success',
      });
    },
  });

  useEffect(() => {
    if (data) {
      setFormState(data);
    }
  }, [data]);

  const hasChanges = useMemo(() => {
    if (!data || !formState) {
      return false;
    }
    return (
      data.email !== formState.email ||
      data.push !== formState.push ||
      data.sms !== formState.sms ||
      data.whatsapp !== formState.whatsapp
    );
  }, [data, formState]);

  const handleToggle = (field: keyof NotificationSettings) => (_: React.ChangeEvent<HTMLInputElement>, checked: boolean) => {
    setFormState((prev) => (prev ? { ...prev, [field]: checked } : prev));
  };

  const handleSave = () => {
    if (!formState) {
      return;
    }
    mutation.mutate(formState);
  };

  const handleCancel = () => {
    if (data) {
      setFormState(data);
    }
  };

  if (isLoading || !formState) {
    return (
      <Box sx={{ display: 'flex', justifyContent: 'center', py: 6 }}>
        <CircularProgress />
      </Box>
    );
  }

  return (
    <Stack spacing={3}>
      <Alert severity="info">
        Estes canais são persistidos no backend e impactam os alertas enviados automaticamente.
      </Alert>
      <Card elevation={2}>
        <CardContent>
          <Stack spacing={3}>
            <Box>
              <Typography variant="h6" gutterBottom>
                Notificações
              </Typography>
              <Typography variant="body2" color="text.secondary">
                Escolha os canais que deseja receber alertas sobre mudanças de preço e disponibilidade.
              </Typography>
            </Box>
            <Divider />
            <FormGroup>
              <FormControlLabel
                control={<Switch checked={formState.email} onChange={handleToggle('email')} />}
                label="Email"
              />
              <FormControlLabel
                control={<Switch checked={formState.push} onChange={handleToggle('push')} />}
                label="Push"
              />
              <FormControlLabel
                control={<Switch checked={formState.sms} onChange={handleToggle('sms')} />}
                label="SMS"
              />
              <FormControlLabel
                control={<Switch checked={formState.whatsapp} onChange={handleToggle('whatsapp')} />}
                label="WhatsApp"
              />
            </FormGroup>
          </Stack>
        </CardContent>
      </Card>
      <SaveBar
        open={hasChanges}
        onSave={handleSave}
        onCancel={handleCancel}
        isSaving={mutation.isPending}
        label="Você tem alterações não salvas em notificações"
      />
    </Stack>
  );
};

export default NotificationsSection;
