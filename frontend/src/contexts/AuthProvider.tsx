import React, { useEffect, useRef, useState, ReactNode } from 'react';
import { authService } from '../services/authService';
import { AuthContext, AuthContextType } from './AuthContext';
import { User } from '../types';
import { clearAccessToken, getAccessToken } from '../utils/authTokens';

/**
 * Provider responsável por manter o estado de autenticação da aplicação.
 * - Gera e fornece: user, isLoading, isAuthenticated, e métodos de ação (login, logout, register, refreshUser).
 * - Carrega o usuário atual ao montar o provider.
 * - Mantém side-effects (armazenamento de tokens, limpeza em erros) encapsulados via authService.
 */
interface AuthProviderProps {
  children: ReactNode;
}

export const AuthProvider: React.FC<AuthProviderProps> = ({ children }) => {
  // Estado do usuário atualmente autenticado (ou null se não houver)
  const [user, setUser] = useState<User | null>(() => {
    if (typeof sessionStorage === 'undefined') {
      return null;
    }
    const cached = sessionStorage.getItem('auth_user');
    if (!cached) {
      return null;
    }
    try {
      return JSON.parse(cached) as User;
    } catch {
      return null;
    }
  });
  // Access token mantido em memória para evitar persistência insegura
  const [accessToken, setAccessTokenState] = useState<string | null>(getAccessToken());
  // Indica se alguma operação de autenticação/recuperação está em andamento
  const [isLoading, setIsLoading] = useState(true);
  const refreshTimeoutRef = useRef<number | null>(null);

  /**
   * Atualiza o cache local do usuário sem persistir tokens
   */
  const persistUser = (nextUser: User | null) => {
    setUser(nextUser);
    if (typeof sessionStorage === 'undefined') {
      return;
    }
    if (nextUser) {
      sessionStorage.setItem('auth_user', JSON.stringify(nextUser));
    } else {
      sessionStorage.removeItem('auth_user');
    }
  };

  /**
   * Decodifica o payload do JWT para extrair a data de expiração
   */
  const parseJwtPayload = (token: string): { exp?: number } | null => {
    const [, payload] = token.split('.');
    if (!payload) {
      return null;
    }
    try {
      const decoded = atob(payload.replace(/-/g, '+').replace(/_/g, '/'));
      return JSON.parse(decoded) as { exp?: number };
    } catch {
      return null;
    }
  };

  /**
   * Agenda refresh automático do token com base no exp do JWT
   */
  const scheduleTokenRefresh = (token: string | null) => {
    if (refreshTimeoutRef.current) {
      window.clearTimeout(refreshTimeoutRef.current);
      refreshTimeoutRef.current = null;
    }
    if (!token) {
      return;
    }
    const payload = parseJwtPayload(token);
    if (!payload?.exp) {
      return;
    }
    const refreshAt = payload.exp * 1000 - 60 * 1000;
    const delay = Math.max(refreshAt - Date.now(), 5 * 1000);
    refreshTimeoutRef.current = window.setTimeout(() => {
      void handleRefreshToken();
    }, delay);
  };

  /**
   * Atualiza o estado do usuário consultando o authService.
   * - Se estiver autenticado, carrega os dados do usuário.
   * - Em caso de erro, limpa tokens e coloca o usuário como null.
   */
  const refreshUser = async () => {
    try {
      // Verifica sessão/token local antes de chamar a API
      if (authService.isAuthenticated()) {
        const userData = await authService.getCurrentUser();
        persistUser(userData);
      } else {
        persistUser(null);
      }
    } catch (error) {
      // Log de erro em PT-BR para facilitar debugging em ambiente local
      console.error('Erro ao carregar usuário:', error);
      persistUser(null);
      // Remove possíveis tokens inválidos/corrompidos da memória
      clearAccessToken();
      setAccessTokenState(null);
    } finally {
      setIsLoading(false);
    }
  };

  /**
   * Atualiza o token acessível ao contexto a partir de authService
   */
  const syncAccessToken = () => {
    const token = getAccessToken();
    setAccessTokenState(token);
    scheduleTokenRefresh(token);
  };

  /**
   * Tenta renovar a sessão ao iniciar o app, utilizando cookie HttpOnly se existir
   */
  const bootstrapSession = async () => {
    setIsLoading(true);
    try {
      await authService.refresh();
      syncAccessToken();
      await refreshUser();
    } catch {
      syncAccessToken();
      persistUser(null);
    } finally {
      setIsLoading(false);
    }
  };

  // Ao montar o provider, tenta recuperar o usuário atual
  useEffect(() => {
    void bootstrapSession();
    return () => {
      if (refreshTimeoutRef.current) {
        window.clearTimeout(refreshTimeoutRef.current);
      }
    };
  }, []);

  useEffect(() => {
    scheduleTokenRefresh(accessToken);
  }, [accessToken]);

  /**
   * Renova o token automaticamente quando estiver perto de expirar
   */
  const handleRefreshToken = async () => {
    try {
      await authService.refresh();
      syncAccessToken();
      await refreshUser();
    } catch (error) {
      console.error('Erro ao renovar sessão:', error);
      await logout();
    }
  };

  /**
   * Realiza o fluxo de login:
   * 1) marca loading
   * 2) chama authService.login que deve armazenar tokens
   * 3) atualiza o usuário com refreshUser
   *
   * Obs: Propaga erros para que componentes consumidores mostrem mensagens apropriadas.
   */
  const login = async (email: string, password: string) => {
    setIsLoading(true);
    try {
      await authService.login(email, password);
      syncAccessToken();
      const userData = await authService.getCurrentUser();
      persistUser(userData);
      return userData;
    } catch (error) {
      setIsLoading(false);
      throw error;
    } finally {
      setIsLoading(false);
    }
  };

  /**
   * Realiza logout:
   * - Chama o serviço de logout (remover tokens do servidor se aplicável)
   * - Limpa estado local do usuário
   * - Garante que o indicador de loading seja atualizado
   */
  const logout = async () => {
    setIsLoading(true);
    try {
      await authService.logout();
      persistUser(null);
      setAccessTokenState(null);
    } catch (error) {
      console.error('Erro ao fazer logout:', error);
    } finally {
      setIsLoading(false);
    }
  };

  /**
   * Registra um novo usuário e realiza login automático após o registro.
   * Obs: em caso de falha no registro, o erro é propagado para o consumidor.
   */
  const register = async (payload: {
    name: string;
    email: string;
    password: string;
    phone_number?: string;
  }) => {
    setIsLoading(true);
    try {
      const registeredUser = await authService.register(payload);
      // Após registro bem-sucedido, faz login automático para habilitar reenvios
      await authService.login(payload.email, payload.password);
      syncAccessToken();
      await refreshUser();
      return registeredUser;
    } catch (error) {
      setIsLoading(false);
      throw error;
    } finally {
      setIsLoading(false);
    }
  };

  // Valor exposto pelo contexto para consumidores
  const value: AuthContextType = {
    user,
    isLoading,
    isAuthenticated: !!accessToken,
    login,
    logout,
    register,
    refreshUser,
    requestEmailVerify: authService.requestEmailVerification,
    requestPhoneOtp: authService.requestPhoneOtp,
    verifyPhoneOtp: authService.verifyPhoneOtp,
    resendVerification: authService.resendVerification,
  };

  // Provider encapsula a árvore de componentes e fornece o estado de autenticação
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
};

// Export default para facilitar importações em componentes de alto nível
export default AuthProvider;
