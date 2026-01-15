/**
 * Seção de notificações dentro da página de configurações
 */

import React, { useEffect, useState } from 'react';
import {
  Box,
  Card,
  CardContent,
  CircularProgress,
  Divider,
  FormControlLabel,
  FormGroup,
  ListItemIcon,
  Stack,
  Switch,
  Typography,
} from '@mui/material';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import NotificationsNoneIcon from '@mui/icons-material/NotificationsNone';
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

  // Mantém uma referência para evitar setState redundante quando o dado já está sincronizado
  const hasInitializedRef = React.useRef(false);

  const mutation = useMutation({
    mutationFn: (payload: NotificationSettings) => updateNotificationSettings(payload),
    onMutate: async (payload) => {
      await queryClient.cancelQueries({ queryKey: ['settings-notifications'] });
      const previous = queryClient.getQueryData<NotificationSettings>(['settings-notifications']);
      queryClient.setQueryData(['settings-notifications'], payload);
      setFormState(payload);
      return { previous };
    },
    onError: (_error, _variables, context) => {
      if (context?.previous) {
        queryClient.setQueryData(['settings-notifications'], context.previous);
        setFormState(context.previous);
      }
      showToast({
        message: 'Não foi possível atualizar as notificações. Tente novamente.',
        severity: 'error',
      });
    },
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
    if (!data) {
      return;
    }
    // Evita renderizações em cascata ao só sincronizar quando há mudança real
    setFormState((prev) => {
      if (!prev) {
        hasInitializedRef.current = true;
        return data;
      }
      const isSame =
        prev.email === data.email &&
        prev.push === data.push &&
        prev.sms === data.sms &&
        prev.whatsapp === data.whatsapp;
      if (isSame && hasInitializedRef.current) {
        return prev;
      }
      hasInitializedRef.current = true;
      return data;
    });
  }, [data]);

  const handleToggle = (field: keyof NotificationSettings) => (_: React.ChangeEvent<HTMLInputElement>, checked: boolean) => {
    setFormState((prev) => {
      if (!prev) {
        return prev;
      }
      const nextState = { ...prev, [field]: checked };
      mutation.mutate(nextState);
      return nextState;
    });
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
      <Card elevation={2}>
        <CardContent>
          <Stack spacing={3}>
            <Box>
              <Stack direction="row" spacing={1.5} alignItems="center">
                <ListItemIcon sx={{ minWidth: 'auto', color: 'text.secondary' }}>
                  <NotificationsNoneIcon fontSize="small" />
                </ListItemIcon>
                <Typography variant="h6">Notificações</Typography>
                {mutation.isPending && <CircularProgress size={16} />}
              </Stack>
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
    </Stack>
  );
};

export default NotificationsSection;
