import React, { createContext, useContext, useState, useEffect } from 'react';

/**
 * Tipo de dados do usuário autenticado
 */
export interface User {
  id: string;
  email: string;
  name?: string;
}

/**
 * Tipo do contexto de autenticação
 */
interface AuthContextType {
  user: User | null;
  token: string | null;
  isLoading: boolean;
  isAuthenticated: boolean;
  login: (email: string, password: string) => Promise<void>;
  logout: () => void;
  setUser: (user: User | null) => void;
  setToken: (token: string | null) => void;
}

/**
 * Criando o contexto de autenticação
 */
const AuthContext = createContext<AuthContextType | undefined>(undefined);

/**
 * Provider de autenticação que envolve a aplicação
 */
export const AuthProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [user, setUser] = useState<User | null>(null);
  const [token, setToken] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  /**
   * Carregando o token e usuário do localStorage ao montar o componente
   */
  useEffect(() => {
    const storedToken = localStorage.getItem('auth_token');
    const storedUser = localStorage.getItem('auth_user');

    if (storedToken && storedUser) {
      try {
        setToken(storedToken);
        setUser(JSON.parse(storedUser));
      } catch (error) {
        console.error('Erro ao carregar autenticação:', error);
        localStorage.removeItem('auth_token');
        localStorage.removeItem('auth_user');
      }
    }

    setIsLoading(false);
  }, []);

  /**
   * Função de login
   */
  const login = async (email: string, password: string) => {
    try {
      const apiUrl = import.meta.env.VITE_FRONTEND_FORGE_API_URL || 'http://localhost:8000';
      const response = await fetch(`${apiUrl}/auth`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/x-www-form-urlencoded',
        },
        body: new URLSearchParams({
          username: email,
          password: password,
        }),
      });

      if (!response.ok) {
        throw new Error('Falha na autenticação');
      }

      const data = await response.json();
      const newToken = data.access_token;

      // Salvando o token
      setToken(newToken);
      localStorage.setItem('auth_token', newToken);

      // Buscando informações do usuário
      const userResponse = await fetch(`${apiUrl}/user`, {
        headers: {
          'Authorization': `Bearer ${newToken}`,
        },
      });

      if (userResponse.ok) {
        const userData = await userResponse.json();
        setUser(userData);
        localStorage.setItem('auth_user', JSON.stringify(userData));
      }
    } catch (error) {
      console.error('Erro ao fazer login:', error);
      throw error;
    }
  };

  /**
   * Função de logout
   */
  const logout = () => {
    setUser(null);
    setToken(null);
    localStorage.removeItem('auth_token');
    localStorage.removeItem('auth_user');
  };

  const value: AuthContextType = {
    user,
    token,
    isLoading,
    isAuthenticated: !!token && !!user,
    login,
    logout,
    setUser,
    setToken,
  };

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
};

/**
 * Hook para usar o contexto de autenticação
 */
export const useAuth = () => {
  const context = useContext(AuthContext);
  if (context === undefined) {
    throw new Error('useAuth deve ser usado dentro de um AuthProvider');
  }
  return context;
};
