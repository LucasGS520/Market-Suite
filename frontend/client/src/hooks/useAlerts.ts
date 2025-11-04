import { useState, useEffect } from 'react';
import { useAuth } from '@/contexts/AuthContext';
import { Alert, getAlerts, markAlertAsRead, deleteAlert } from '@/lib/api';

/**
 * Hook para gerenciar alertas
 */
export const useAlerts = () => {
  const { token } = useAuth();
  const [alerts, setAlerts] = useState<Alert[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const fetchAlerts = async () => {
    if (!token) return;

    setIsLoading(true);
    setError(null);

    try {
      const data = await getAlerts(token);
      setAlerts(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Erro ao buscar alertas');
    } finally {
      setIsLoading(false);
    }
  };

  const handleMarkAsRead = async (alertId: string) => {
    if (!token) return;

    try {
      await markAlertAsRead(token, alertId);
      setAlerts(alerts.map(a => (a.id === alertId ? { ...a, is_read: true } : a)));
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Erro ao marcar alerta como lido');
    }
  };

  const handleDeleteAlert = async (alertId: string) => {
    if (!token) return;

    try {
      await deleteAlert(token, alertId);
      setAlerts(alerts.filter(a => a.id !== alertId));
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Erro ao deletar alerta');
    }
  };

  useEffect(() => {
    fetchAlerts();
  }, [token]);

  return {
    alerts,
    isLoading,
    error,
    refetch: fetchAlerts,
    markAsRead: handleMarkAsRead,
    deleteAlert: handleDeleteAlert,
  };
};
