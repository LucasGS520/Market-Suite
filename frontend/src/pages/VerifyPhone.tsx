/**
 * Página de verificação de telefone com OTP
 */

import React, { useState } from 'react';
import { useSearchParams, Link as RouterLink } from 'react-router-dom';
import {
  Alert,
  Box,
  Button,
  Container,
  Paper,
  TextField,
  Typography,
} from '@mui/material';
import { AxiosError } from 'axios';
import { authService } from '../services/authService';
import { useAuth } from '../hooks/useAuth';
import { ApiErrorResponse } from '../types';
import ResendButton from '../components/ResendButton';

const VerifyPhone: React.FC = () => {
  const [searchParams] = useSearchParams();
  const defaultUserId = searchParams.get('userId') ?? '';
  const { isAuthenticated } = useAuth();

  const [userId, setUserId] = useState(defaultUserId);
  const [otp, setOtp] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [success, setSuccess] = useState(false);
  const [error, setError] = useState('');

  const handleSubmit = async (event: React.FormEvent) => {
    event.preventDefault();
    setError('');
    setSuccess(false);

    if (!userId.trim()) {
      setError('Informe o ID do usuário para continuar');
      return;
    }
    if (otp.trim().length !== 6) {
      setError('Informe o código de verificação de 6 dígitos');
      return;
    }

    setIsLoading(true);

    try {
      await authService.verifyPhoneOtp(userId, otp);
      setSuccess(true);
    } catch (err) {
      const axiosError = err as AxiosError<ApiErrorResponse>;
      setError(axiosError.response?.data?.detail || 'Não foi possível validar o código.');
    } finally {
      setIsLoading(false);
    }
  };

  const handleResend = async () => {
    try {
      await authService.requestPhoneOtp();
    } catch (err) {
      const axiosError = err as AxiosError<ApiErrorResponse>;
      setError(axiosError.response?.data?.detail || 'Não foi possível reenviar o código.');
      throw err;
    }
  };

  return (
    <Container maxWidth="sm">
      <Box
        sx={{
          marginTop: 8,
          display: 'flex',
          flexDirection: 'column',
          alignItems: 'center',
        }}
      >
        <Paper elevation={3} sx={{ padding: 4, width: '100%' }}>
          <Typography component="h1" variant="h5" align="center" gutterBottom>
            Verificação de telefone
          </Typography>

          {success && (
            <Alert severity="success" sx={{ mb: 2 }}>
              Telefone verificado com sucesso.
            </Alert>
          )}

          {error && (
            <Alert severity="error" sx={{ mb: 2 }}>
              {error}
            </Alert>
          )}

          <Box component="form" onSubmit={handleSubmit}>
            <TextField
              margin="normal"
              fullWidth
              required
              label="ID do usuário"
              value={userId}
              onChange={(event) => setUserId(event.target.value)}
              disabled={isLoading}
            />
            <TextField
              margin="normal"
              fullWidth
              required
              label="Código OTP"
              value={otp}
              onChange={(event) => setOtp(event.target.value)}
              inputProps={{ maxLength: 6, inputMode: 'numeric', pattern: '\\d*' }}
              disabled={isLoading}
            />
            <Button
              type="submit"
              variant="contained"
              fullWidth
              sx={{ mt: 2 }}
              disabled={isLoading}
            >
              Verificar
            </Button>
          </Box>

          <Box sx={{ mt: 3 }}>
            <ResendButton
              label="Reenviar código"
              onResend={handleResend}
              disabled={!isAuthenticated}
            />
            {!isAuthenticated && (
              <Alert severity="info" sx={{ mt: 2 }}>
                Para reenviar o código, faça login na sua conta.
              </Alert>
            )}
          </Box>

          <Button
            component={RouterLink}
            to="/login"
            variant="text"
            fullWidth
            sx={{ mt: 2 }}
          >
            Voltar para login
          </Button>
        </Paper>
      </Box>
    </Container>
  );
};

export default VerifyPhone;
