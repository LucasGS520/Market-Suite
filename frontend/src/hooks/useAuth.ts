import { useContext } from 'react';
import { AuthContext } from '../contexts/AuthProvider';

/**
 * Hook personalizado para acessar o AuthContext sem repetir lógica de verificação.
 * Garante que componentes sejam sempre renderizados dentro do AuthProvider.
 */
export const useAuth = () => {
  const context = useContext(AuthContext);

  if (!context) {
    throw new Error('useAuth deve ser usado dentro de um AuthProvider');
  }

  return context;
};
