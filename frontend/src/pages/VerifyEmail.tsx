/**
 * Página responsável por confirmar a verificação do email via token
 */

import React, { useEffect, useState } from 'react';
import { useSearchParams, Link as RouterLink } from 'react-router-dom';
import { Alert, Box, Button, CircularProgress, Container, Paper, Typography } from '@mui/material';
import { AxiosError } from 'axios';
import { authService } from '../services/authService';
import { ApiErrorResponse } from '../types';

const VerifyEmail: React.FC = () => {
  const [searchParams] = useSearchParams();
  const token = searchParams.get('token');
  const [status, setStatus] = useState<'idle' | 'loading' | 'success' | 'error'>('idle');
  const [errorMessage, setErrorMessage] = useState<string>('');

  useEffect(() => {
    if (!token) {
      setStatus('error');
      setErrorMessage('Token de verificação não encontrado.');
      return;
    }

    const verifyToken = async () => {
      setStatus('loading');
      try {
        await authService.confirmEmailVerification(token);
        setStatus('success');
      } catch (error) {
        const axiosError = error as AxiosError<ApiErrorResponse>;
        setErrorMessage(axiosError.response?.data?.detail || 'Não foi possível verificar o e-mail.');
        setStatus('error');
      }
    };

    void verifyToken();
  }, [token]);

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
            Verificação de e-mail
          </Typography>

            {status === 'loading' && (
              <Box sx={{ display: 'flex', justifyContent: 'center', my: 3 }}>
                <CircularProgress />
              </Box>
            )}

            {status === 'success' && (
              <Alert severity="success" sx={{ mb: 3 }}>
                E-mail verificado com sucesso.
              </Alert>
            )}

            {status === 'error' && (
                <Alert severity="error" sx={{ mb: 3 }}>
                  {errorMessage}
                </Alert>
            )}

            <Button
              component={RouterLink}
              to="/login"
              variant="contained"
              fullWidth
            >
              Ir para Login
            </Button>
        </Paper>
      </Box>
    </Container>
  );
};

export default VerifyEmail;
