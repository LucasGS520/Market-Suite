import apiClient from '../lib/api';
import { TokenPair, User } from '../types';

/**
 * Serviço de autenticação do frontend.
 *
 * Este módulo encapsula chamadas à API relacionadas à autenticação
 * (login, logout, registro, recuperação de senha, verificação de email, etc.)
 * e também gerencia o armazenamento simples de tokens no localStorage.
 */
export const authService = {
  /**
   * Realiza login com email (username) e senha.
   *
   * Envia um form-url-encoded para a rota /auth e, em caso de sucesso,
   * persiste os tokens retornados no localStorage.
   */
  async login(email: string, password: string): Promise<TokenPair> {
    // Usamos FormData para simular body x-www-form-urlencoded requisitado pelo backend.
    const formData = new FormData();
    formData.append('username', email);
    formData.append('password', password);

    const response = await apiClient.post<TokenPair>('/auth', formData, {
      headers: {
        'Content-Type': 'application/x-www-form-urlencoded',
      },
    });

    // Salvar tokens no localStorage para uso nas próximas requisições.
    localStorage.setItem('access_token', response.data.access_token);
    localStorage.setItem('refresh_token', response.data.refresh_token);

    return response.data;
  },

  /**
   * Realiza logout do usuário e tenta revogar o refresh token no backend.
   * - Se houver um refresh_token em localStorage, envia uma requisição para /auth/logout.
   * - Independentemente do resultado da revogação, remove os tokens do localStorage.
   */
  async logout(): Promise<void> {
    const refreshToken = localStorage.getItem('refresh_token');

    if (refreshToken) {
      try {
        await apiClient.post('/auth/logout', {
          refresh_token: refreshToken,
        });
      } catch (error) {
        // Log de erro não-bloqueante: a limpeza local ainda é realizada.
        // Preferir logger estruturado (ex: structlog) em produção.
        console.error('Erro ao revogar token:', error);
      }
    }

    // Limpar tokens localmente para efetivar logout no frontend.
    localStorage.removeItem('access_token');
    localStorage.removeItem('refresh_token');
  },

  /**
   * Registra um novo usuário no sistema.
   */
  async register(email: string, password: string, name?: string): Promise<User> {
    const response = await apiClient.post<User>('/users', {
      email,
      password,
      name,
    });

    return response.data;
  },

  /**
   * Obtém os dados do usuário atualmente autenticado.
   */
  async getCurrentUser(): Promise<User> {
    const response = await apiClient.get<User>('/users/me');
    return response.data;
  },

  /**
   * Solicita o início do fluxo de recuperação de senha.
   *
   * Envia um email de recuperação conforme fluxo do backend.
   */
  async requestPasswordReset(email: string): Promise<void> {
    await apiClient.post('/auth/reset_password/request', { email });
  },

  /**
   * Confirma a recuperação de senha usando o token enviado por email.
   */
  async confirmPasswordReset(token: string, newPassword: string): Promise<void> {
    await apiClient.post('/auth/reset_password/confirm', {
      token,
      new_password: newPassword,
    });
  },

  /**
   * Altera a senha do usuário atualmente autenticado.
   */
  async changePassword(currentPassword: string, newPassword: string): Promise<void> {
    await apiClient.post('/auth/profile/change-password', {
      current_password: currentPassword,
      new_password: newPassword,
    });
  },

  /**
   * Solicita o envio de email de verificação ao usuário autenticado.
   * O backend deve enviar o email contendo o token/URL de verificação.
   */
  async requestEmailVerification(): Promise<void> {
    await apiClient.post('/auth/verify/request');
  },

  /**
   * Confirma a verificação de email utilizando o token recebido.
   */
  async confirmEmailVerification(token: string): Promise<void> {
    await apiClient.post('/auth/verify/confirm', { token });
  },

  /**
   * Indica se existe um token de acesso armazenado localmente.
   *
   * Nota: Esta verificação é apenas local (presença do token) e não valida
   * se o token expirou. Verificações mais robustas devem chamar uma rota
   * de validação/refresh ou inspecionar o JWT.
   */
  isAuthenticated(): boolean {
    return !!localStorage.getItem('access_token');
  },
};
