/**
 * Página de Login
 *
 * Componente responsável pela interface de autenticação do usuário.
 * - Mantém os estados dos campos de email/senha, flags de loading e mensagens de erro.
 * - Chama o contexto de autenticação (useAuth) para realizar o login.
 * - Após login bem-sucedido redireciona para /dashboard.
 */

import React, { useState } from 'react';
import { useNavigate, Link } from 'react-router-dom';
import {
  Container,
  Box,
  TextField,
  Button,
  Typography,
  Paper,
  Alert,
  CircularProgress,
} from '@mui/material';
import { AxiosError } from 'axios';
import { useAuth } from '../hooks/useAuth';
import { ApiErrorResponse } from '../types';
import VerificationPrompt from '../components/VerificationPrompt';

/**
 * Componente de tela de Login.
 * Usa o contexto de autenticação para realizar a ação de login.
 */
const Login: React.FC = () => {
  const navigate = useNavigate();
  const { login, requestEmailVerify, requestPhoneOtp } = useAuth();

  // Estado para o campo de email (string)
  const [email, setEmail] = useState('');

  // Estado para o campo de senha (string)
  const [password, setPassword] = useState('');

  // Mensagem de erro exibida ao usuário (vazia quando não há erro)
  const [error, setError] = useState('');

  // Flag de carregamento para desabilitar inputs e mostrar spinner
  const [isLoading, setIsLoading] = useState(false);
  const [pendingUserId, setPendingUserId] = useState<string | null>(null);
  const [pendingEmail, setPendingEmail] = useState<string>('');
  const [pendingPhone, setPendingPhone] = useState<string | null>(null);

  /**
   * Manipulador de submit do formulário.
   * - Prevê comportamento padrão do form.
   * - Reseta mensagem de erro, ativa loading.
   * - Chama login(email, password) proveniente do contexto.
   * - Em caso de sucesso, navega para /dashboard.
   * - Em caso de falha, tenta extrair mensagem do response e exibi-la; caso contrário exibe uma mensagem genérica de erro.
   */
  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError('');
    setPendingUserId(null);
    setPendingEmail('');
    setPendingPhone(null);
    setIsLoading(true);

    try {
      const user = await login(email, password);
      const isPending =
        !!user &&
        (user.status === 'pending' ||
          !user.email_verified ||
          (!!user.phone_number && !user.phone_number_verified));

      if (user && isPending) {
        setPendingUserId(user.id);
        setPendingEmail(user.email);
        setPendingPhone(user.phone_number ?? null);
        return;
      }

      // Redireciona para dashboard após login bem-sucedido
      navigate('/dashboard');
    } catch (err: unknown) {
      // Tenta extrair mensagem detalhada do backend (se existir), caso contrário usa mensagem padrão
      const axiosError = err as AxiosError<ApiErrorResponse>;
      const detailMessage = axiosError.response?.data?.detail;

      setError(detailMessage || 'Erro ao fazer login. Verifique suas credenciais.');
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <Container maxWidth="sm">
      {/* Box centralizador para layout vertical com espaçamento */}
      <Box
        sx={{
          marginTop: 8,
          display: 'flex',
          flexDirection: 'column',
          alignItems: 'center',
        }}
      >
        {/* Paper que contém o card do formulário */}
        <Paper elevation={3} sx={{ padding: 4, width: '100%' }}>
          <Typography component="h1" variant="h4" align="center" gutterBottom>
            Market Suite
          </Typography>
          <Typography component="h2" variant="h6" align="center" gutterBottom>
            Login
          </Typography>

          {/* Mostra erro caso exista */}
          {error && (
            <Alert severity="error" sx={{ mb: 2 }}>
              {error}
            </Alert>
          )}

          {pendingUserId && (
            <VerificationPrompt
              email={pendingEmail}
              userId={pendingUserId}
              phoneNumber={pendingPhone}
              onResendEmail={requestEmailVerify}
              onResendPhone={requestPhoneOtp}
            />
          )}
          {pendingUserId && (
            <Button
              fullWidth
              variant="outlined"
              sx={{ mt: 2 }}
              onClick={() => navigate('/dashboard')}
            >
              Continuar para o Dashboard
            </Button>
          )}

          {/* Formulário controlado */}
          {!pendingUserId && (
            <Box component="form" onSubmit={handleSubmit} sx={{ mt: 1 }}>
              <TextField
                margin="normal"
                required
                fullWidth
                id="email"
                label="Email"
                name="email"
                autoComplete="email"
                autoFocus
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                disabled={isLoading} // Desabilita durante loading
              />
              <TextField
                margin="normal"
                required
                fullWidth
                name="password"
                label="Senha"
                type="password"
                id="password"
                autoComplete="current-password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                disabled={isLoading} // Desabilita durante loading
              />
              <Button
                type="submit"
                fullWidth
                variant="contained"
                sx={{ mt: 3, mb: 2 }}
                disabled={isLoading}
              >
                {/* Mostra spinner durante operação de login */}
                {isLoading ? <CircularProgress size={24} /> : 'Entrar'}
              </Button>

              {/* Link para a tela de registro */}
              <Box sx={{ textAlign: 'center' }}>
                <Link to="/register" style={{ textDecoration: 'none' }}>
                  <Typography variant="body2" color="primary">
                    Não tem uma conta? Registre-se
                  </Typography>
                </Link>
              </Box>
            </Box>
          )}
        </Paper>
      </Box>
    </Container>
  );
};

export default Login;
