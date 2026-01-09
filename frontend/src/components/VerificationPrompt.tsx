/**
 * Componente de prompt para orientar usuários pendentes a verificar email/telefone
 */

import React, { useState } from 'react';
import { Alert, Box, Card, CardContent, Stack, Typography, Button } from '@mui/material';
import { AxiosError } from 'axios';
import { Link as RouterLink } from 'react-router-dom';
import ResendButton from './ResendButton';
import { ApiErrorResponse } from '../types';

interface VerificationPromptProps {
  email: string;
  userId?: string;
  phoneNumber?: string | null;
  onResendEmail: () => Promise<void>;
  onResendPhone: () => Promise<void>;
  disableResend?: boolean;
}

const VerificationPrompt: React.FC<VerificationPromptProps> = ({
  email,
  userId,
  phoneNumber,
  onResendEmail,
  onResendPhone,
  disableResend = false,
}) => {
  const [feedback, setFeedback] = useState<{ severity: 'success' | 'error'; message: string } | null>(null);

  const handleResendEmail = async () => {
    try {
      await onResendEmail();
      setFeedback({ severity: 'success', message: 'Código enviado com sucesso.' });
    } catch (error) {
      const axiosError = error as AxiosError<ApiErrorResponse>;
      setFeedback({
        severity: 'error',
        message: axiosError.response?.data?.detail || 'Não foi possível enviar o código.',
      });
      throw error;
    }
  };

  return (
    <Box sx={{ mt: 3 }}>
      <Alert severity="info" sx={{ mb: 3 }}>
        Sua conta está pendente. Por favor, verifique seu email ou telefone para continuar.
      </Alert>
      {feedback && (
        <Alert severity="info" sx={{ mb: 3 }}>
          {feedback.message}
        </Alert>
      )}

      <Stack spacing={2}>
        <Card elevation={2}>
          <CardContent>
            <Typography variant="h6" gutterBottom>
              Verificação por e-mail
            </Typography>
            <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
              Enviado para {email}, verifique seu email para continuar. Caso não tenha recebido, solicite o reenvio abaixo.
            </Typography>
            <ResendButton
              label="Reenviar e-mail de verificação"
              onResend={handleResendEmail}
              disabled={disableResend}
            />
          </CardContent>
        </Card>

        {phoneNumber && (
          <Card elevation={2}>
            <CardContent>
              <Typography variant="h6" gutterBottom>
                Verificação por telefone
              </Typography>
              <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
                Código SMS enviado para {phoneNumber}, insira o código na tela de verificação. Caso não tenha recebido, solicite o reenvio abaixo.
              </Typography>
              <Stack spacing={2}>
                <ResendButton
                  label="Enviar código por telefone"
                  onResend={handleResendPhone}
                  disabled={disableResend}
                />
                {userId && (
                  <Button
                    variant="outlined"
                    component={RouterLink}
                    to={`/verify-phone?userId=${userId}`}
                    fullWidth
                  >
                    Confirmar código
                  </Button>
                )}
              </Stack>
            </CardContent>
          </Card>
        )}
      </Stack>
    </Box>
  );
};

export default VerificationPrompt;
