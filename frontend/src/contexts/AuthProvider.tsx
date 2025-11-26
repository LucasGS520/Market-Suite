import React, { useState, useEffect, ReactNode } from 'react';
import { authService } from '../services/authService';
import { AuthContext, AuthContextType } from './AuthContext';
import { User } from '../types';

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
  const [user, setUser] = useState<User | null>(null);
  // Indica se alguma operação de autenticação/recuperação está em andamento
  const [isLoading, setIsLoading] = useState(true);

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
        setUser(userData);
      } else {
        setUser(null);
      }
    } catch (error) {
      // Log de erro em PT-BR para facilitar debugging em ambiente local
      console.error('Erro ao carregar usuário:', error);
      setUser(null);
      // Remove possíveis tokens inválidos/corrompidos do localStorage
      localStorage.removeItem('access_token');
      localStorage.removeItem('refresh_token');
    } finally {
      setIsLoading(false);
    }
  };

  // Ao montar o provider, tenta recuperar o usuário atual
  useEffect(() => {
    refreshUser();
  }, []);

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
      await refreshUser();
    } catch (error) {
      setIsLoading(false);
      throw error;
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
      setUser(null);
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
  const register = async (email: string, password: string, name?: string) => {
    setIsLoading(true);
    try {
      await authService.register(email, password, name);
      // Após registro bem-sucedido, faz login automático
      await login(email, password);
    } catch (error) {
      setIsLoading(false);
      throw error;
    }
  };

  // Valor exposto pelo contexto para consumidores
  const value: AuthContextType = {
    user,
    isLoading,
    isAuthenticated: !!user,
    login,
    logout,
    register,
    refreshUser,
  };

  // Provider encapsula a árvore de componentes e fornece o estado de autenticação
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
};

// Export default para facilitar importações em componentes de alto nível
export default AuthProvider;
