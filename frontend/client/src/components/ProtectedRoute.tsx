import React, { useEffect } from 'react';
import { useAuth } from '@/contexts/AuthContext';
import { useLocation } from 'wouter';
import { Loader2 } from 'lucide-react';

interface ProtectedRouteProps {
  children: React.ReactNode;
}

/**
 * Componente que protege rotas que requerem autenticação.
 * - Exibe um loader enquanto o estado de autenticação está sendo verificado.
 * - Redireciona para /login quando o usuário não está autenticado.
 * - Renderiza os filhos quando o usuário está autenticado.
 */
export const ProtectedRoute: React.FC<ProtectedRouteProps> = ({ children }) => {
  // Obtemos o estado de autenticação do contexto (isAuthenticated e isLoading).
  const { isAuthenticated, isLoading } = useAuth();

  // useLocation do wouter retorna [location, navigate]; usamos apenas a função de navegação.
  const [, navigate] = useLocation();

  // Enquanto carregando, mostramos um indicador de loading centralizado.
  if (isLoading) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <Loader2 className="h-8 w-8 animate-spin" />
      </div>
    );
  }

  // Evitamos executar navegação diretamente durante a renderização para não causar efeitos colaterais.
  // Usamos useEffect para realizar o redirecionamento quando não autenticado.
  useEffect(() => {
    if (!isLoading && !isAuthenticated) {
      // Redireciona o usuário para a página de login
      navigate('/login');
    }
    // dependências: reexecutar quando mudar o estado de autenticação ou o carregamento
  }, [isLoading, isAuthenticated, navigate]);

  // Enquanto o redirect não acontece (ou logo após ele), não renderizamos a rota protegida.
  if (!isAuthenticated) {
    return null;
  }

  // Usuário autenticado: renderiza o conteúdo protegido.
  return <>{children}</>;
};
