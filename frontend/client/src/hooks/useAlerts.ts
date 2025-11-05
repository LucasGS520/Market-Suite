import { useState, useEffect } from 'react';
import { useAuth } from '@/contexts/AuthContext';
import { Alert, getAlerts } from '@/lib/api';

/**
 * Hook para gerenciar alertas do usuário.
 *
 * Fornece funcionalidade para:
 *  - Expõe operações locais para ocultar itens caso usuário deseje limpar a visualização.
 *
 * Retorna o estado dos alertas, sinalizadores de carregamento/erro e funções utilitárias.
 */
export const useAlerts = () => {
  // Token de autenticação provido pelo contexto
  const { token } = useAuth();

  // Estado com a lista de alertas atualmente carregados
  const [alerts, setAlerts] = useState<Alert[]>([]);

  // Conjunto com IDs ocultados manualmente para mater comportamento local de "limpeza"
  const [hiddenAlertIds, setHiddenAlertIds] = useState<Set<string>>(new Set());

  // Indicador de carregamento durante chamadas à API
  const [isLoading, setIsLoading] = useState(false);

  // Mensagem de erro (null quando não há erro)
  const [error, setError] = useState<string | null>(null);

  // Busca os alertas no backend. Não faz nada se não houver token.
  const fetchAlerts = async () => {
    if (!token) return;

    // Inicia o estado de carregamento e limpa erros anteriores
    setIsLoading(true);
    setError(null);

    try {
      // Chamada à API para obter alertas e atualização do estado local
      const data = await getAlerts(token);
      setAlerts(data);
      // Ao buscar novamente, reexibe todos os itens ocultados anteriormente
      setHiddenAlertIds(new Set());
    } catch (err) {
      // Registra mensagem de erro legível para exibição na UI
      setError(err instanceof Error ? err.message : 'Erro ao buscar alertas');
    } finally {
      setIsLoading(false);
    }
  };

  /** 
   * Remove um alerta da renderização local sem chamar o backend.
   * Mantém compatibilidade com iterações de UI enquanto a API não oferece suporte de mutação.
   */
  const handleHideAlert = (alertId: string) => {
    setHiddenAlertIds((prev) => new Set(prev).add(alertId));
  };

  // Ao montar o hook ou quando o token mudar, busca os alertas
  useEffect(() => {
    fetchAlerts();
    // Intencionalmente deixamos fetchAlerts fora das dependências para evitar re-criações desnecessárias.
  }, [token]);

  // API pública do hook para o componente consumidor
  return {
    alerts: alerts.filter((alert) => !hiddenAlertIds.has(alert.id)),
    isLoading,
    error,
    refetch: fetchAlerts,
    hideAlert: handleHideAlert,
  };
};
