import React, { createContext, useContext, useState, useEffect } from 'react';

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
  isLoading: boolean;
  isAuthenticated: boolean;
  login: (email: string, password: string) => Promise<void>;
  logout: () => void;
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
  // Indicador de carregamento inicial (leitura do localStorage)
  const [isLoading, setIsLoading] = useState(true);

  /**
   * Ao montar, tenta carregar credenciais do localStorage.
   * Se os dados estiverem presentes e válidos, restaura o estado.
   * Em caso de erro (parse inválido), limpa o localStorage.
   */
  useEffect(() => {
    const storedToken = localStorage.getItem('auth_token');
    const storedUser = localStorage.getItem('auth_user');

    if (storedToken && storedUser) {
      try {
        setToken(storedToken);
        setUser(JSON.parse(storedUser));
      } catch (error) {
        // Em caso de dados corrompidos, remove itens para evitar loops futuros
        console.error('Erro ao carregar autenticação:', error);
        localStorage.removeItem('auth_token');
        localStorage.removeItem('auth_user');
      }
    }

    // Carregamento inicial concluído
    setIsLoading(false);
  }, []);

  /**
   * Função de login:
   * - Faz POST para /auth usando form-urlencoded para obter access_token
   * - Armazena token no estado e localStorage
   * - Em seguida consulta /users/me com o token para obter dados do usuário
   *
   * Lança erro em falha de autenticação para que o chamador possa tratar.
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
        // Propaga erro para UI (ex.: mostrar mensagem ao usuário)
        throw new Error('Falha na autenticação');
      }

      const data = await response.json();
      const newToken = data.access_token;

      // Salva token no estado e persistência local
      setToken(newToken);
      localStorage.setItem('auth_token', newToken);

      // Busca informações do usuário com o token obtido
      const userResponse = await fetch(`${apiUrl}/users/me`, {
        headers: {
          Authorization: `Bearer ${newToken}`,
        },
      });

      if (userResponse.ok) {
        const userData = await userResponse.json();
        setUser(userData);
        localStorage.setItem('auth_user', JSON.stringify(userData));
      } else if (userResponse.status === 401) {
        // Limpa credenciais inválidas para evitar sessão inconsistente
        logout();
        throw new Error('Sessão expirada. Faça login novamente.');
      } else {
        throw new Error('Falha ao carregar dados do usuário');
      }
    } catch (error) {
      // Loga o erro e repassa para o chamador tratar (ex.: mostrar toast)
      console.error('Erro ao fazer login:', error);
      throw error;
    }
  };

  /**
   * Função de logout:
   * - Limpa estado do usuário e token
   * - Remove credenciais do localStorage
   */
  const logout = () => {
    setUser(null);
    setToken(null);
    localStorage.removeItem('auth_token');
    localStorage.removeItem('auth_user');
  };

  // Valor do contexto disponibilizado para consumidores
  const value: AuthContextType = {
    user,
    token,
    isLoading,
    // isAuthenticated verdadeiro somente se houver token e usuário carregados
    isAuthenticated: !!token && !!user,
    login,
    logout,
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
