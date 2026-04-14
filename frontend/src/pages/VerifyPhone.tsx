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
  Stack,
  TextField,
  Typography,
} from '@mui/material';
import { authService } from '../services/authService';
import { useAuth } from '../hooks/useAuth';
import { getApiErrorDetail } from '../utils/apiErrors';
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

  /**
   * Envia o OTP de verificação e mantém o usuário autenticado durante o fluxo
   */
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
      setError(getApiErrorDetail(err, 'Não foi possível validar o código.'));
    } finally {
      setIsLoading(false);
    }
  };

  /**
   * Reenvia o código de verificação por telefone quando o usuário está autenticado
   */
  const handleResend = async () => {
    try {
      await authService.requestPhoneOtp();
    } catch (err) {
      setError(getApiErrorDetail(err, 'Não foi possível reenviar o código.'));
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

          <Alert severity="warning" sx={{ mt: 3 }}>
            Você pode continuar a navegação sem verificação, mas alguns recursos podem ficar limitados até concluir a validação.
          </Alert>

          <Stack spacing={2} sx={{ mt: 2 }}>
            <Button
              component={RouterLink}
              to="/dashboard"
              variant="contained"
              fullWidth
            >
              Voltar ao Dashboard
            </Button>
            <Button
              component={RouterLink}
              to="/login"
              variant="text"
              fullWidth
            >
              Voltar para Login
            </Button>
          </Stack>
        </Paper>
      </Box>
    </Container>
  );
};

export default VerifyPhone;
