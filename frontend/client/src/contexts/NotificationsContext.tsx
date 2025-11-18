import React, { createContext, useCallback, useContext, useMemo } from 'react';
import type { ComparisonSummary, PriceComparisonAlert } from '@/lib/api';

/**
 * Conexão de notificações em tempo real, mantida como stub enquanto o WebSocket está desativado.
 */
export type NotificationConnectionState = 'idle' | 'connecting' | 'connected' | 'error';

/** Evento de comparação criado pelo backend, contendo resumo e alertas derivados. */
export interface ComparisonCreatedEvent {
  type: 'comparison.created';
  monitored_id: string;
  comparison_id: string | null;
  summary?: ComparisonSummary | null;
  alerts?: PriceComparisonAlert[] | null;
  created_at?: string;
  task_id?: string | null;
  trace_id?: string | null;
}

/** Evento de alerta criado pelo backend, indicando notificação enviada ao usuário. */
export interface AlertCreatedEvent {
  type: 'alert.created';
  notification_id?: string | null;
  user_id?: string | null;
  alert_rule_id?: string | null;
  comparison_id?: string | null;
  channel?: string | null;
  status?: string | null;
  success?: boolean;
  created_at?: string | null;
  subject?: string | null;
  message?: string | null;
  severity?: string | null;
  alert_type?: string | null;
  monitored_id?: string | null;
}

/** União dos eventos relevantes suportados pelo provider. */
export type NotificationEvent = ComparisonCreatedEvent | AlertCreatedEvent;

/** Função chamada ao receber eventos após filtros opcionais. */
export type NotificationEventHandler = (event: NotificationEvent) => void;

/** Estrutura exposta via contexto para inscrição e monitoramento da conexão. */
export interface NotificationsContextValue {
  connectionState: NotificationConnectionState;
  isConnected: boolean;
  subscribe: (handler: NotificationEventHandler) => () => void;
  subscribeToMonitored: (monitoredId: string, handler: NotificationEventHandler) => () => void;
}

/** Contexto compartilhado contendo estado da conexão e utilitários de inscrição. */
const NotificationsContext = createContext<NotificationsContextValue | undefined>(undefined);

/**
 * Provider com implementação *no-op* para manter a API estável enquanto o streaming está desativado.
 */
export const NotificationsProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const subscribe = useCallback((handler: NotificationEventHandler) => {
    // Mantemos um stub para preservar assinatura esperada sem registrar listeners reais.
    return () => {
      // Retorno de cleanup intencionalmente vazio.
    };
  }, []);

  const subscribeToMonitored = useCallback(
    (_monitoredId: string, handler: NotificationEventHandler) => {
      // Fallback equivalente ao subscribe geral para evitar quebra de chamadas existentes.
      return subscribe(handler);
    },
    [subscribe],
  );

  const value = useMemo<NotificationsContextValue>(
    () => ({
      connectionState: 'idle',
      isConnected: false,
      subscribe,
      subscribeToMonitored,
    }),
    [subscribe, subscribeToMonitored],
  );

  return <NotificationsContext.Provider value={value}>{children}</NotificationsContext.Provider>;
};

/** Hook utilitário para acessar o contexto de notificações e garantir disponibilidade. */
export const useNotificationsContext = (): NotificationsContextValue => {
  const context = useContext(NotificationsContext);
  if (!context) {
    throw new Error('useNotificationsContext deve ser usado dentro de NotificationsProvider.');
  }
  return context;
};
