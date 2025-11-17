import { useEffect } from 'react';
import {
  type NotificationEventHandler,
  type NotificationsContextValue,
  useNotificationsContext,
} from '@/contexts/NotificationsContext';

/**
 * Parâmetros aceitos pelo hook `useNotifications` para inscrição declarativa.
 */
export interface UseNotificationsOptions {
  /** Identificador do produto monitorado para escopo automático do listener. */
  monitoredId?: string;
  /** Função opcional chamada sempre que um evento é recebido. */
  onEvent?: NotificationEventHandler;
}

/**
 * Estrutura de retorno do hook com estado da conexão e utilitários públicos.
 */
export interface UseNotificationsResult extends NotificationsContextValue {}

/**
 * Hook que encapsula o contexto de notificações e registra listeners automaticamente.
 */
export const useNotifications = (options: UseNotificationsOptions = {}): UseNotificationsResult => {
  const context = useNotificationsContext();
  const { monitoredId, onEvent } = options;

  useEffect(() => {
    if (!onEvent) {
      return;
    }

    if (monitoredId) {
      return context.subscribeToMonitored(monitoredId, onEvent);
    }

    return context.subscribe(onEvent);
  }, [context, monitoredId, onEvent]);

  return context;
};
