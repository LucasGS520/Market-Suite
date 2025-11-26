/**
 * Componente responsável por proteger rotas que exigem autenticação.
 * - Exibe um indicador de carregamento enquanto o estado de autenticação é verificado.
 * - Redireciona para /login caso o usuário não esteja autenticado.
 * - Renderiza os children quando o usuário está autenticado.
 */

import React from 'react';
import { Navigate } from 'react-router-dom';
import { useAuth } from '../hooks/useAuth';
import { CircularProgress, Box } from '@mui/material';

interface ProtectedRouteProps {
  /**
   * Conteúdo protegido que será renderizado se o usuário estiver autenticado.
   */
  children: React.ReactNode;
}

/**
 * Componente funcional que protege rotas que requerem autenticação.
 *
 * Comportamento:
 * - Enquanto `isLoading` for true, renderiza um spinner centralizado ocupando a
 *   altura mínima da tela para indicar que a verificação está em progresso.
 * - Se a verificação terminar e `isAuthenticated` for false, redireciona o usuário
 *   para a rota de login (`/login`) utilizando `Navigate` com `replace` para
 *   evitar histórico de navegação indesejado.
 * - Se autenticado, renderiza os `children` fornecidos.
 */
const ProtectedRoute: React.FC<ProtectedRouteProps> = ({ children }) => {
  // Obtém estado de autenticação e indicador de carregamento do contexto de Auth.
  const { isAuthenticated, isLoading } = useAuth();

  // Enquanto o estado de autenticação está sendo carregado, exibe um loader.
  if (isLoading) {
    return (
      <Box
        display="flex"
        justifyContent="center"
        alignItems="center"
        minHeight="100vh"
      >
        <CircularProgress />
      </Box>
    );
  }

  // Se não estiver autenticado, redireciona para a tela de login.
  if (!isAuthenticated) {
    return <Navigate to="/login" replace />;
  }

  // Usuário autenticado: renderiza o conteúdo protegido.
  return <>{children}</>;
};

export default ProtectedRoute;
