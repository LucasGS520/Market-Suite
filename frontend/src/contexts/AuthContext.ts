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
  login: (email: string, password: string) => Promise<User | null>;
  logout: () => Promise<void>;
  register: (payload: {
    name: string;
    email: string;
    password: string;
    phone_number?: string;
  }) => Promise<User>;
  refreshUser: () => Promise<void>;
  requestEmailVerify: () => Promise<void>;
  requestPhoneOtp: () => Promise<void>;
  verifyPhoneOtp: (userId: string, otp: string) => Promise<void>;
  resendVerification: (channel: 'email' | 'phone_number') => Promise<void>;
}

// Contexto isolado do componente para atender a regra do react-refresh
export const AuthContext = createContext<AuthContextType | undefined>(undefined);
