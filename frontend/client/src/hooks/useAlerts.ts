import { useState, useEffect } from 'react';
import { useAuth } from '@/contexts/AuthContext';
import { Alert, getAlerts, markAlertAsRead, deleteAlert } from '@/lib/api';

/**
 * Hook para gerenciar alertas do usuário.
 *
 * Fornece funcionalidade para:
 *  - Buscar alertas da API
 *  - Marcar um alerta como lido
 *  - Deletar um alerta
 *
 * Retorna o estado dos alertas, sinalizadores de carregamento/erro e funções de ação.
 */
export const useAlerts = () => {
  // Token de autenticação provido pelo contexto
  const { token } = useAuth();

  // Estado com a lista de alertas atualmente carregados
  const [alerts, setAlerts] = useState<Alert[]>([]);

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
    } catch (err) {
      // Registra mensagem de erro legível para exibição na UI
      setError(err instanceof Error ? err.message : 'Erro ao buscar alertas');
    } finally {
      setIsLoading(false);
    }
  };

  // Marca um alerta como lido no backend e atualiza o estado local
  const handleMarkAsRead = async (alertId: string) => {
    if (!token) return;

    try {
      await markAlertAsRead(token, alertId);
      // Atualiza localmente o campo is_read para refletir a mudança
      setAlerts(alerts.map(a => (a.id === alertId ? { ...a, is_read: true } : a)));
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Erro ao marcar alerta como lido');
    }
  };

  // Deleta um alerta no backend e remove do estado local
  const handleDeleteAlert = async (alertId: string) => {
    if (!token) return;

    try {
      await deleteAlert(token, alertId);
      // Remove o alerta deletado da lista local
      setAlerts(alerts.filter(a => a.id !== alertId));
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Erro ao deletar alerta');
    }
  };

  // Ao montar o hook ou quando o token mudar, busca os alertas
  useEffect(() => {
    fetchAlerts();
    // Intencionalmente deixamos fetchAlerts fora das dependências para evitar re-criações desnecessárias.
  }, [token]);

  // API pública do hook para o componente consumidor
  return {
    alerts,
    isLoading,
    error,
    refetch: fetchAlerts,
    markAsRead: handleMarkAsRead,
    deleteAlert: handleDeleteAlert,
  };
};
