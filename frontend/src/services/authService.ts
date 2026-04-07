import apiClient from '../lib/api';
import {
  clearAccessToken,
  getAccessToken,
  setAccessToken,
} from '../utils/authTokens';
import { TokenPair, User } from '../types';

/**
 * Serviço de autenticação do frontend.
 *
 * Este módulo encapsula chamadas à API relacionadas à autenticação
 * (login, logout, registro, recuperação de senha, verificação de email, etc.)
 * e mantém o access_token em memória para reduzir exposição local.
 */
export const authService = {
  /**
   * Realiza login com email (username) e senha.
   *
   * Envia um form-url-encoded para a rota /auth e, em caso de sucesso,
   * armazena o access_token em memória e confia no cookie HttpOnly do backend.
   */
  async login(email: string, password: string): Promise<TokenPair> {
    // Usamos FormData para simular body x-www-form-urlencoded requisitado pelo backend.
    const formData = new FormData();
    formData.append('username', email);
    formData.append('password', password);

    const response = await apiClient.post<TokenPair>('/auth/login', formData, {
      headers: {
        'Content-Type': 'application/x-www-form-urlencoded',
      },
    });

    // Salvar access token somente em memória para reduzir exposição local.
    setAccessToken(response.data.access_token);
     return response.data;
  },

  /**
   * Realiza logout do usuário e tenta revogar o refresh token no backend.
   * - Envia requisição para /auth/logout para revogar o cookie HttpOnly no backend.
   * - Independentemente do resultado, remove tokens mantidos em memória.
   */
  async logout(): Promise<void> {
    try {
      await apiClient.post('/auth/logout');
    } catch (error) {
      // Log de erro não-bloqeuante: limpeza local ainda é realizada
      // Preferir logger estruturado (ex.: structlog) em produção
      console.error('Erro ao revogar token:', error);
    }

    // Limpar tokens localmente para efetivar logout no frontend.
    clearAccessToken();
  },

  /**
   * Registra um novo usuário no sistema.
   */
  async register(payload: {
    email: string;
    password: string;
    name: string;
    phone_number?: string;
  }): Promise<User> {
    const response = await apiClient.post<User>('/users/', {
      email: payload.email,
      password: payload.password,
      name: payload.name,
      phone_number: payload.phone_number,
    });

    return response.data;
  },

  /**
   * Solicita um novo access_token usando refresh token via cookie HttpOnly.
   */
  async refresh(): Promise<TokenPair> {
    // A rota /auth/refresh aceita apenas POST; evitar GET preserva o contrato do backend
    const response = await apiClient.post<TokenPair>('/auth/refresh');
    setAccessToken(response.data.access_token);
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
    await apiClient.post('/users/resend-verification', { channel: 'email' });
  },

  /**
   * Confirma a verificação de email utilizando o token recebido.
   */
  async confirmEmailVerification(token: string): Promise<void> {
    await apiClient.post('/auth/verify-email', null, { params: { token } });
  },

  /**
   * Indica se existe um token de acesso armazenado localmente.
   *
   * Esta checagem depende do token em memória gerenciado pelos utilitários
   * de autenticação, mantendo o acesso fora do armazenamento persistente.
   * Nota: Esta verificação é apenas local (presença do token) e não valida
   * se o token expirou. Verificações mais robustas devem chamar uma rota
   * de validação/refresh ou inspecionar o JWT.
   */
  isAuthenticated(): boolean {
    return !!getAccessToken();
  },

  /**
   * Solicita o envio de OTP por telefone para o usuário autenticado.
   */
  async requestPhoneOtp(): Promise<void> {
    await apiClient.post('/users/resend-verification', { channel: 'phone_number' });
  },

  /**
   * Confirma o OTP de telefone utilizando user_id e otp.
   */
  async verifyPhoneOtp(userId: string, otp: string): Promise<void> {
    await apiClient.post('/auth/verify-phone', { user_id: userId, otp });
  },

  /**
   * Reenvia tokens de verificação com base no canal informado.
   */
  async resendVerification(channel: 'email' | 'phone_number'): Promise<void> {
    await apiClient.post('/users/resend-verification', { channel });
  },
};
