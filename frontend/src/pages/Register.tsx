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
import { useAuth } from '../contexts/AuthContext';

/**
 * Componente de registro de usuário.
 *
 * Renderiza um formulário com campos: nome (opcional), email, senha e confirmar senha.
 * Faz validações simples no cliente antes de chamar o método register do contexto de autenticação.
 */
const Register: React.FC = () => {
  const navigate = useNavigate();
  const { register } = useAuth();

  // Estados controlados para os campos do formulário
  const [name, setName] = useState<string>('');
  const [email, setEmail] = useState<string>('');
  const [password, setPassword] = useState<string>('');
  const [confirmPassword, setConfirmPassword] = useState<string>('');

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

    // Validação: senhas devem coincidir
    if (password !== confirmPassword) {
      setError('As senhas não coincidem');
      return;
    }

    // Validação: senha mínima (cliente)
    if (password.length < 6) {
      setError('A senha deve ter pelo menos 6 caracteres');
      return;
    }

    setIsLoading(true);

    try {
      // Chamada ao serviço de autenticação (implementado no contexto)
      await register(email, password, name);
      // Redireciona o usuário para o dashboard após registro bem-sucedido
      navigate('/dashboard');
    } catch (err: any) {
      // Tenta extrair mensagem detalhada da resposta; senão, mostra mensagem genérica
      setError(
        err?.response?.data?.detail ||
          'Erro ao criar conta. Tente novamente.'
      );
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

          {/* Formulário de registro */}
          <Box component="form" onSubmit={handleSubmit} sx={{ mt: 1 }}>
            {/* Nome (opcional) */}
            <TextField
              margin="normal"
              fullWidth
              id="name"
              label="Nome (opcional)"
              name="name"
              autoComplete="name"
              autoFocus
              value={name}
              onChange={(e) => setName(e.target.value)}
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
            {/* Confirmação de senha */}
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

            {/* Link para a página de login */}
            <Box sx={{ textAlign: 'center' }}>
              <Link to="/login" style={{ textDecoration: 'none' }}>
                <Typography variant="body2" color="primary">
                  Já tem uma conta? Faça login
                </Typography>
              </Link>
            </Box>
          </Box>
        </Paper>
      </Box>
    </Container>
  );
};

export default Register;
