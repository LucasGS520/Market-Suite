/**
 * Página de registro de usuário do frontend (React + MUI).
 * 
 * Este componente apresenta o formulário para criação de conta,
 * realiza validações básicas no cliente (senhas iguais e tamanho mínimo)
 * e delega a criação ao contexto de autenticação (useAuth).
 * - Em caso de sucesso, redireciona para /dashboard.
 * - Em caso de erro, exibe uma mensagem amigável ao usuário.
 */

import React, { useState } from 'react';
import { Link } from 'react-router-dom';
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
 * Componente de registro de usuário.
 *
 * Renderiza um formulário com campos: nome, sobrenome (opcional), email, senha e confirmar senha.
 * Faz validações simples no cliente antes de chamar o método register do contexto de autenticação.
 */
const Register: React.FC = () => {
  const { register, requestEmailVerify, requestPhoneOtp } = useAuth();

  // Estados controlados para os campos do formulário
  const [name, setName] = useState<string>('');
  const [lastName, setLastName] = useState<string>('');
  const [email, setEmail] = useState<string>('');
  const [phone, setPhone] = useState<string>('');
  const [password, setPassword] = useState<string>('');
  const [confirmPassword, setConfirmPassword] = useState<string>('');
  const [registeredUserId, setRegisteredUserId] = useState<string | null>(null);

  // Estado para exibir mensagens de erro ao usuário
  const [error, setError] = useState<string>('');
  // Estado para indicar carregamento durante a requisição de registro
  const [isLoading, setIsLoading] = useState<boolean>(false);

  /**
   * Manipulador do envio do formulário.
   * - Valida se as senhas coincidem e o tamanho mínimo.
   * - Chama register(email, password, name) do contexto de autenticação.
   * - Navega para /dashboard em caso de sucesso.
   * - Exibe erro amigável em caso de falha.
   */
  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError('');
    setRegisteredUserId(null);

    // Validação: senhas devem coincidir
    if (password !== confirmPassword) {
      setError('As senhas não coincidem');
      return;
    }

    // Validação: senha mínima (cliente)
    if (password.length < 8) {
      setError('A senha deve ter pelo menos 8 caracteres');
      return;
    }
    if (!/[A-Za-z]/.test(password) || !/\d/.test(password)) {
      setError('A senha deve conter letras e números');
      return;
    }

    if (!name.trim()) {
      setError('Informe seu nome para continuar');
      return;
    }

    setIsLoading(true);

    try {
      // Chamada ao serviço de autenticação (implementado no contexto)
      const fullName = lastName ? `${name.trim()} ${lastName.trim()}`.trim() : name.trim();
      const user = await register({
        name: fullName,
        email,
        password,
        phone_number: phone || undefined,
      });
      setRegisteredUserId(user.id);
    } catch (err: unknown) {
      // Tenta extrair mensagem detalhada da resposta; senão, mostra mensagem genérica
      const axiosError = err as AxiosError<ApiErrorResponse>;
      const detailMessage = axiosError.response?.data?.detail;

      setError(detailMessage || 'Erro ao criar conta. Tente novamente.');
    } finally {
      setIsLoading(false);
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
          {/* Títulos da página */}
          <Typography component="h1" variant="h4" align="center" gutterBottom>
            Market Suite
          </Typography>
          <Typography component="h2" variant="h6" align="center" gutterBottom>
            Criar Conta
          </Typography>

          {/* Exibe alerta de erro quando houver mensagem */}
          {error && (
            <Alert severity="error" sx={{ mb: 2 }}>
              {error}
            </Alert>
          )}

          {registeredUserId && (
            <>
              <Alert severity="success" sx={{ mb: 2 }}>
                Cadastro concluído! Finalize a sua verificação para ativar sua conta e acessar todos os recursos.
              </Alert>
            <VerificationPrompt
              email={email}
              userId={registeredUserId}
              phoneNumber={phone || null}
              onResendEmail={requestEmailVerify}
              onResendPhone={requestPhoneOtp}
            />
            </>
          )}

          {/* Formulário de registro */}
          {!registeredUserId && (
            <Box component="form" onSubmit={handleSubmit} sx={{ mt: 1 }}>
              {/* Nome */}
              <TextField
                margin="normal"
                required
                fullWidth
                id="name"
                label="Nome"
                name="name"
                autoComplete="name"
                autoFocus
                value={name}
                onChange={(e) => setName(e.target.value)}
                disabled={isLoading}
              />
              <TextField
                margin="normal"
                fullWidth
                id="lastName"
                label="Sobrenome (opcional)"
                name="lastName"
                autoComplete="family-name"
                value={lastName}
                onChange={(e) => setLastName(e.target.value)}
                disabled={isLoading}
              />

              {/* Email obrigatório */}
              <TextField
                margin="normal"
                required
                fullWidth
                id="email"
                label="Email"
                name="email"
                autoComplete="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                disabled={isLoading}
              />
              
              {/* Telefone opcional */}
              <TextField
                margin="normal"
                fullWidth
                id="phone"
                label="Telefone (opcional)"
                name="phone"
                autoComplete="tel"
                value={phone}
                onChange={(e) => setPhone(e.target.value)}
                disabled={isLoading}
              />

              {/* Senha */}
              <TextField
                margin="normal"
                required
                fullWidth
                name="password"
                label="Senha"
                type="password"
                id="password"
                autoComplete="new-password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                disabled={isLoading}
              />

              {/* Confirmar Senha */}
              <TextField
                margin="normal"
                required
                fullWidth
                name="confirmPassword"
                label="Confirmar Senha"
                type="password"
                id="confirmPassword"
                autoComplete="new-password"
                value={confirmPassword}
                onChange={(e) => setConfirmPassword(e.target.value)}
                disabled={isLoading}
              />

              {/* Botão de envio com indicador de carregamento */}
              <Button
                type="submit"
                fullWidth
                variant="contained"
                sx={{ mt: 3, mb: 2 }}
                disabled={isLoading}
              >
                {isLoading ? <CircularProgress size={24} /> : 'Criar Conta'}
              </Button>

              {/* Link para página de login */}
              <Box sx={{ textAlign: 'center' }}>
                <Link to="/login" style={{ textDecoration: 'none' }}>
                  <Typography variant="body2" color="primary">
                    Já tem uma conta? Entre aqui
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

export default Register;
