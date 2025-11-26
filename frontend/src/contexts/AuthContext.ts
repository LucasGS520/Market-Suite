import { createContext } from 'react';
import { User } from '../types';

/**
 * Contexto responsável por representar o estado de autenticação compartilhado.
 * Armazena a estrutura de dados consumida pelos hooks e providers.
 */
export interface AuthContextType {
  user: User | null;
  isLoading: boolean;
  isAuthenticated: boolean;
  login: (email: string, password: string) => Promise<void>;
  logout: () => Promise<void>;
  register: (email: string, password: string, name?: string) => Promise<void>;
  refreshUser: () => Promise<void>;
}

// Contexto isolado do componente para atender a regra do react-refresh
export const AuthContext = createContext<AuthContextType | undefined>(undefined);
