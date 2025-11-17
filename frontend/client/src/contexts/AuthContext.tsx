import React, { createContext, useContext, useState, useEffect, useCallback } from 'react';
import { useLocation } from 'wouter';
import { toast } from 'sonner';
import {
  SESSION_EXPIRED_EVENT,
  TOKENS_REFRESHED_EVENT,
  apiRequest,
  clearStoredTokens,
  getStoredAccessToken,
  getStoredRefreshToken,
  isTokenExpired,
  login as loginRequest,
  persistTokens,
  refreshTokens,
} from '@/lib/api';

/**
 * Tipo de dados do usuário autenticado
 */
export interface User {
  /** Identificador único do usuário */
  id: string;
  /** Email do usuário (usado para login/autenticação) */
  email: string;
  /** Nome opcional do usuário para exibição */
  name?: string;
}

/**
 * Tipo do contexto de autenticação contendo estado e ações.
 */
interface AuthContextType {
  user: User | null;
  token: string | null;
  refreshToken: string | null;
  isLoading: boolean;
  isAuthenticated: boolean;
  login: (email: string, password: string) => Promise<void>;
  logout: () => void;
  refreshSession: () => Promise<string | null>;
  getFreshAccessToken: () => Promise<string | null>;
  setUser: (user: User | null) => void;
  setToken: (token: string | null) => void;
}

/**
 * Contexto de autenticação (inicialmente indefinido até o Provider envolver a árvore).
 */
const AuthContext = createContext<AuthContextType | undefined>(undefined);

/**
 * Provider de autenticação que envolve a aplicação e disponibiliza
 * estado e ações de login/logout para componentes filhos.
 */
export const AuthProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  // Estado do usuário autenticado (ou null quando deslogado)
  const [user, setUser] = useState<User | null>(null);
  // Token JWT recebido do backend (ou null quando ausente)
  const [token, setToken] = useState<string | null>(null);
  const [refreshToken, setRefreshToken] = useState<string | null>(null);
  // Indicador de carregamento inicial (leitura do localStorage)
  const [isLoading, setIsLoading] = useState(true);
  // Função de navegação do Wouter para redirecionamentos globais
  const [, navigate] = useLocation();

  /**
   * Ao montar, tenta carregar credenciais do localStorage.
   * Se os dados estiverem presentes e válidos, restaura o estado.
   * Em caso de erro (parse inválido), limpa o localStorage.
   */
  useEffect(() => {
    const storedToken = getStoredAccessToken();
    const storedRefresh = getStoredRefreshToken();
    const storedUser = typeof window !== 'undefined' ? localStorage.getItem('auth_user') : null;

    if (storedToken && storedUser) {
      try {
        setToken(storedToken);
        if (storedRefresh) {
          setRefreshToken(storedRefresh);
        }
        setUser(JSON.parse(storedUser));
      } catch (error) {
        // Em caso de dados corrompidos, remove itens para evitar loops futuros
        console.error('Erro ao carregar autenticação:', error);
        clearStoredTokens();
        localStorage.removeItem('auth_user');
      }
    }

    // Carregamento inicial concluído
    setIsLoading(false);
  }, []);

  /**
   * Função de login:
   * - Usa o utilitário login da camada de API para obter o access_token preservando mensagens do backend
   * - Armazena token no estado e localStorage
   * - Em seguida consulta /users/me com o token para obter dados do usuário
   *
   * Lança erro em falha de autenticação preservando o detail vindo da API quando disponível.
   */
  const login = async (email: string, password: string) => {
    let newToken: string | null = null;
    let newRefresh: string | null = null;
    try {
      const authTokens = await loginRequest(email, password);
      newToken = authTokens.access_token;
      newRefresh = authTokens.refresh_token;

      // Persistimos o token imediatamente para habilitar chamadas autenticadas subsequentes
      setToken(newToken);
      setRefreshToken(newRefresh);
      persistTokens(newToken, newRefresh);

      const userData = await apiRequest<User>('/users/me', {
        token: newToken,
      });

      setUser(userData);
      localStorage.setItem('auth_user', JSON.stringify(userData));
    } catch (error) {
      // Limpa credenciais temporárias caso o fluxo tenha falhado após obter o token
      if (newToken || newRefresh) {
        logout();
      }
      console.error('Erro ao fazer login:', error);
      
      if (error instanceof Error) {
        throw error;
      }

      throw new Error('Erro desconhecido ao fazer login');
    }
  };

  /**
   * Função de logout:
   * - Limpa estado do usuário e token
   * - Remove credenciais do localStorage
   */
  const logout = useCallback(() => {
    setUser(null);
    setToken(null);
    setRefreshToken(null);
    clearStoredTokens();
    localStorage.removeItem('auth_user');
  }, []);

  /**
   * Efetua refresh silencioso quando houver refreshToken válido.
   */
  const refreshSession = useCallback(async (): Promise<string | null> => {
    if (!refreshToken) {
      return null;
    }

    try {
      const refreshed = await refreshTokens(refreshToken);
      setToken(refreshed.access_token);
      setRefreshToken(refreshed.refresh_token);
      return refreshed.access_token;
    } catch (error) {
      console.error('Erro ao renovar sessão.', error);
      logout();
      return null;
    }
  }, [logout, refreshToken]);

  /**
   * Obtém o token mais recente, disparando refresh se estiver expirado.
   */
  const getFreshAccessToken = useCallback(async (): Promise<string | null> => {
    if (!token) {
      return null;
    }

    if (!isTokenExpired(token)) {
      return token;
    }

    return refreshSession();
  }, [refreshSession, token]);

  useEffect(() => {
    /**
     * Listener global que trata respostas 401 emitidas pelo cliente HTTP.
     *
     * - Executa logout para limpar estado local/localStorage
     * - Redireciona para a tela de login
     * - Exibe toast informando a expiração de sessão
     */
    const handleSessionExpired = () => {
      logout();
      toast.error('Sessão expirada');
      navigate('/login');
    };

    if (typeof window === 'undefined') {
      return;
    }

    window.addEventListener(SESSION_EXPIRED_EVENT, handleSessionExpired);
    return () => {
      window.removeEventListener(SESSION_EXPIRED_EVENT, handleSessionExpired);
    };
  }, [logout, navigate]);

  useEffect(() => {
    if (typeof window === 'undefined') {
      return undefined;
    }

    const handleTokensRefreshed = (event: Event) => {
      const custom = event as CustomEvent<{ access_token?: string; refresh_token?: string }>;
      const accessToken = custom.detail?.access_token ?? null;
      const updatedRefresh = custom.detail?.refresh_token ?? null;

      if (accessToken) {
        setToken(accessToken);
      }

      if (updatedRefresh) {
        setRefreshToken(updatedRefresh);
      }
    };

    window.addEventListener(TOKENS_REFRESHED_EVENT, handleTokensRefreshed);

    return () => {
      window.removeEventListener(TOKENS_REFRESHED_EVENT, handleTokensRefreshed);
    };
  }, []);

  // Valor do contexto disponibilizado para consumidores
  const value: AuthContextType = {
    user,
    token,
    refreshToken,
    isLoading,
    // isAuthenticated verdadeiro somente se houver token e usuário carregados
    isAuthenticated: !!token && !!user,
    login,
    logout,
    refreshSession,
    getFreshAccessToken,
    setUser,
    setToken,
  };

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
};

/**
 * Hook useAuth:
 * - Facilita o acesso ao contexto de autenticação
 * - Lança erro se usado fora do AuthProvider para ajudar no desenvolvimento
 */
export const useAuth = () => {
  const context = useContext(AuthContext);
  if (context === undefined) {
    throw new Error('useAuth deve ser usado dentro de um AuthProvider');
  }
  return context;
};
