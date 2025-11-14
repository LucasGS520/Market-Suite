import React, {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
} from 'react';
import { useLocation } from 'wouter';
import { useQueryClient, type InfiniteData } from '@tanstack/react-query';
import { toast } from 'sonner';
import {
  SESSION_EXPIRED_EVENT,
  buildNotificationsWebSocketUrl,
  getMonitoredProduct,
  type ComparisonSummary,
  type MonitoredProduct,
  type PaginatedMonitoredProducts,
  type PriceComparisonAlert,
} from '@/lib/api';
import { useAuth } from '@/contexts/AuthContext';

/**
 * Estado atual da conexão WebSocket para consumo de notificações em tempo real.
 */
export type NotificationConnectionState = 'idle' | 'connecting' | 'connected' | 'error';

/**
 * Evento de comparação criado pelo backend, contendo resumo e alertas derivados.
 */
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

/**
 * Evento de alerta criado pelo backend, indicando notificação enviada ao usuário.
 */
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

/**
 * União dos eventos relevantes suportados pelo provider.
 */
export type NotificationEvent = ComparisonCreatedEvent | AlertCreatedEvent;

/**
 * Função chamada ao receber eventos após filtros opcionais.
 */
export type NotificationEventHandler = (event: NotificationEvent) => void;

/**
 * Estrutura exposta via contexto para inscrição e monitoramento da conexão.
 */
export interface NotificationsContextValue {
  connectionState: NotificationConnectionState;
  isConnected: boolean;
  subscribe: (handler: NotificationEventHandler) => () => void;
  subscribeToMonitored: (monitoredId: string, handler: NotificationEventHandler) => () => void;
}

/**
 * Contexto compartilhado contendo estado da conexão e utilitários de inscrição.
 */
const NotificationsContext = createContext<NotificationsContextValue | undefined>(undefined);

/**
 * Estrutura interna para armazenar listeners gerais e específicos por monitorado.
 */
type ListenerRegistry = {
  general: Set<NotificationEventHandler>;
  byMonitored: Map<string, Set<NotificationEventHandler>>;
};

/**
 * Calcula um atraso de reconexão exponencial com limite superior.
 */
const computeBackoffDelay = (attempt: number): number => {
  const cappedAttempt = Math.min(attempt, 6);
  const baseDelay = 1000 * 2 ** cappedAttempt;
  return Math.min(baseDelay, 30_000);
};

/**
 * Normaliza valores numéricos que podem chegar como string do backend.
 */
const toNumberOrNull = (value: unknown): number | null => {
  if (value === null || value === undefined) {
    return null;
  }

  if (typeof value === 'number') {
    return Number.isFinite(value) ? value : null;
  }

  if (typeof value === 'string') {
    const parsed = Number(value);
    return Number.isFinite(parsed) ? parsed : null;
  }

  return null;
};

/**
 * Provider responsável por manter a conexão WebSocket e distribuir eventos.
 */
export const NotificationsProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const { token, user } = useAuth();
  const queryClient = useQueryClient();
  const [, navigate] = useLocation();

  const [connectionState, setConnectionState] = useState<NotificationConnectionState>('idle');
  const websocketRef = useRef<WebSocket | null>(null);
  const reconnectAttemptRef = useRef(0);
  const reconnectTimeoutRef = useRef<number | null>(null);
  const isManuallyClosedRef = useRef(false);

  const listenersRef = useRef<ListenerRegistry>({
    general: new Set(),
    byMonitored: new Map(),
  });

  const activeMonitoredChannelsRef = useRef<Map<string, number>>(new Map());
  const processedEventsRef = useRef<Map<string, number>>(new Map());

  /**
   * Remove eventos antigos do cache de deduplicação para evitar crescimento indefinido.
   */
  const pruneProcessedEvents = useCallback(() => {
    const registry = processedEventsRef.current;
    const now = Date.now();

    for (const [key, timestamp] of registry.entries()) {
      if (now - timestamp > 5 * 60_000) {
        registry.delete(key);
      }
    }

    if (registry.size <= 200) {
      return;
    }

    const entries = Array.from(registry.entries()).sort((a, b) => a[1] - b[1]);
    for (const [key] of entries.slice(0, registry.size - 200)) {
      registry.delete(key);
    }
  }, []);

  /**
   * Marca um evento como processado evitando tratar duplicados em reconexões.
   */
  const markEventAsProcessed = useCallback(
    (event: NotificationEvent): boolean => {
      const eventKeyCandidates: string[] = [];

      if (event.type === 'comparison.created') {
        if (event.comparison_id) {
          eventKeyCandidates.push(`comparison:${event.comparison_id}`);
        }
        if (event.task_id) {
          eventKeyCandidates.push(`task:${event.task_id}`);
        }
      } else if (event.type === 'alert.created') {
        if (event.notification_id) {
          eventKeyCandidates.push(`notification:${event.notification_id}`);
        }
        if (event.alert_rule_id && event.created_at) {
          eventKeyCandidates.push(`rule:${event.alert_rule_id}:${event.created_at}`);
        }
      }

      if (eventKeyCandidates.length === 0) {
        return true;
      }

      const registry = processedEventsRef.current;
      const now = Date.now();

      for (const key of eventKeyCandidates) {
        const existing = registry.get(key);
        if (existing && now - existing < 2 * 60_000) {
          return false;
        }
      }

      for (const key of eventKeyCandidates) {
        registry.set(key, now);
      }

      pruneProcessedEvents();
      return true;
    },
    [pruneProcessedEvents],
  );

  /**
   * Converte dados do resumo de comparação em campos atualizados do produto.
   */
  const mapSummaryToProductPatch = useCallback((summary: ComparisonSummary | null | undefined) => {
    if (!summary) {
      return {};
    }

    return {
      current_price: toNumberOrNull(summary.monitored_price),
      competitors_count: typeof summary.competitors_count === 'number' ? summary.competitors_count : null,
      competitors_with_price_count:
        typeof summary.competitors_with_price_count === 'number'
          ? summary.competitors_with_price_count
          : null,
      competitors_mean: toNumberOrNull(summary.competitors_mean),
      competitors_min: toNumberOrNull(summary.competitors_min),
      competitors_max: toNumberOrNull(summary.competitors_max),
      position_rank: toNumberOrNull(summary.position_rank),
      potential_savings: toNumberOrNull(summary.potential_savings),
      comparison_insights: summary.comparison_insights ?? null,
      last_comparison_at: summary.last_comparison_at ?? null,
    } satisfies Partial<MonitoredProduct>;
  }, []);

  /**
   * Atualiza o cache da lista de monitorados mesclando dados recebidos em tempo real.
   */
  const patchCachedMonitoredProduct = useCallback(
    (monitoredId: string, patch: Partial<MonitoredProduct>) => {
      const cacheKey = ['monitored-products', token] as const;

      queryClient.setQueryData<InfiniteData<PaginatedMonitoredProducts>>(cacheKey, (data) => {
        if (!data) {
          return data;
        }

        const nextPages = data.pages.map((page) => ({
          ...page,
          items: page.items.map((item) => {
            if (item.id !== monitoredId) {
              return item;
            }

            return {
              ...item,
              ...patch,
            };
          }),
        }));

        return {
          ...data,
          pages: nextPages,
        };
      });
    },
    [queryClient, token],
  );

  /**
   * Efetua carregamento direto do backend caso o cache não possua o item esperado.
   */
  const refetchMonitoredFromApi = useCallback(
    async (monitoredId: string): Promise<void> => {
      if (!token) {
        return;
      }

      try {
        const fresh = await getMonitoredProduct(token, monitoredId);
        patchCachedMonitoredProduct(monitoredId, fresh);
      } catch (error) {
        console.error('Falha ao atualizar produto monitorado após evento em tempo real.', error);
      }
    },
    [patchCachedMonitoredProduct, token],
  );

  /**
   * Localiza o identificador do monitorado associado ao evento recebido.
   */
  const resolveMonitoredIdFromEvent = useCallback(
    (event: NotificationEvent): string | null => {
      if (event.type === 'comparison.created') {
        return event.monitored_id;
      }

      if (event.type === 'alert.created') {
        if (event.monitored_id) {
          return event.monitored_id;
        }

        if (event.comparison_id) {
          const cacheKey = ['monitored-products', token] as const;
          const cached = queryClient.getQueryData<InfiniteData<PaginatedMonitoredProducts>>(cacheKey);
          if (!cached) {
            return null;
          }

          for (const page of cached.pages) {
            for (const item of page.items) {
              if (item.latest_comparison_id === event.comparison_id) {
                return item.id;
              }
            }
          }
        }
      }

      return null;
    },
    [queryClient, token],
  );

  /**
   * Aplica atualizações de cache e notifica listeners específicos.
   */
  const dispatchEventToListeners = useCallback(
    async (event: NotificationEvent) => {
      if (!markEventAsProcessed(event)) {
        return;
      }

      let monitoredId: string | null = null;
      if (event.type === 'comparison.created') {
        monitoredId = event.monitored_id;
        const patch = {
          ...mapSummaryToProductPatch(event.summary ?? null),
          latest_comparison_id: event.comparison_id ?? null,
        } as Partial<MonitoredProduct>;

        patchCachedMonitoredProduct(event.monitored_id, patch);
      } else if (event.type === 'alert.created') {
        monitoredId = resolveMonitoredIdFromEvent(event);
        if (monitoredId) {
          await refetchMonitoredFromApi(monitoredId);
        }
      }

      const { general, byMonitored } = listenersRef.current;
      general.forEach((handler) => handler(event));

      if (monitoredId) {
        const scopedHandlers = byMonitored.get(monitoredId);
        scopedHandlers?.forEach((handler) => handler(event));
      }
    },
    [mapSummaryToProductPatch, markEventAsProcessed, patchCachedMonitoredProduct, refetchMonitoredFromApi, resolveMonitoredIdFromEvent],
  );

  /**
   * Exibe toast informativo quando alertas são emitidos.
   */
  const notifyAlertViaToast = useCallback(
    (event: AlertCreatedEvent, monitoredId: string | null) => {
      if (!event.message) {
        return;
      }

      toast.warning(`Alerta: ${event.message}`, {
        duration: 6_000,
        action: monitoredId
          ? {
              label: 'Ver detalhes',
              onClick: () => {
                navigate(`/competitors/${monitoredId}`);
              },
            }
          : undefined,
      });
    },
    [navigate],
  );

  /**
   * Trata mensagens recebidas do WebSocket, despachando apenas eventos úteis.
   */
  const handleMessage = useCallback(
    async (event: MessageEvent) => {
      let parsed: unknown;
      try {
        parsed = JSON.parse(event.data);
      } catch (error) {
        console.warn('Mensagem WS inválida recebida (não é JSON).', error);
        return;
      }

      if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) {
        return;
      }

      const payload = parsed as Record<string, unknown>;
      const type = payload.type;

      if (type === 'comparison.created') {
        const comparisonEvent: ComparisonCreatedEvent = {
          type: 'comparison.created',
          monitored_id: String(payload.monitored_id ?? ''),
          comparison_id: payload.comparison_id ? String(payload.comparison_id) : null,
          summary: (payload.summary as ComparisonSummary | null) ?? null,
          alerts: (payload.alerts as PriceComparisonAlert[] | null) ?? null,
          created_at: payload.created_at ? String(payload.created_at) : undefined,
          task_id: payload.task_id ? String(payload.task_id) : null,
          trace_id: payload.trace_id ? String(payload.trace_id) : null,
        };

        await dispatchEventToListeners(comparisonEvent);
        return;
      }

      if (type === 'alert.created') {
        const alertEvent: AlertCreatedEvent = {
          type: 'alert.created',
          notification_id: payload.notification_id ? String(payload.notification_id) : null,
          user_id: payload.user_id ? String(payload.user_id) : null,
          alert_rule_id: payload.alert_rule_id ? String(payload.alert_rule_id) : null,
          comparison_id: payload.comparison_id ? String(payload.comparison_id) : null,
          channel: payload.channel ? String(payload.channel) : null,
          status: payload.status ? String(payload.status) : null,
          success: payload.success === undefined ? true : Boolean(payload.success),
          created_at: payload.created_at ? String(payload.created_at) : null,
          subject: payload.subject ? String(payload.subject) : null,
          message: payload.message ? String(payload.message) : null,
          severity: payload.severity ? String(payload.severity) : null,
          alert_type: payload.alert_type ? String(payload.alert_type) : null,
          monitored_id: payload.monitored_id ? String(payload.monitored_id) : null,
        };

        const monitoredId = resolveMonitoredIdFromEvent(alertEvent);
        await dispatchEventToListeners(alertEvent);
        notifyAlertViaToast(alertEvent, monitoredId);
        return;
      }

      if (type === 'session.expired') {
        window.dispatchEvent(new CustomEvent(SESSION_EXPIRED_EVENT));
        return;
      }
    },
    [dispatchEventToListeners, notifyAlertViaToast, resolveMonitoredIdFromEvent],
  );

  /**
   * Solicita inscrição nos canais monitorados que possuem listeners ativos.
   */
  const syncChannelSubscriptions = useCallback(() => {
    const socket = websocketRef.current;
    if (!socket || socket.readyState !== WebSocket.OPEN) {
      return;
    }

    const pendingChannels = Array.from(activeMonitoredChannelsRef.current.keys()).map(
      (monitoredId) => `monitored:${monitoredId}`,
    );

    if (pendingChannels.length === 0) {
      return;
    }

    socket.send(
      JSON.stringify({
        action: 'subscribe',
        channels: pendingChannels,
      }),
    );
  }, []);

  /**
   * Agenda nova tentativa de conexão utilizando backoff exponencial.
   */
  const scheduleReconnect = useCallback(
    (lastClose?: CloseEvent) => {
      if (!token || isManuallyClosedRef.current) {
        return;
      }

      if (lastClose && [4401, 4403].includes(lastClose.code)) {
        window.dispatchEvent(new CustomEvent(SESSION_EXPIRED_EVENT));
        return;
      }

      const nextAttempt = reconnectAttemptRef.current + 1;
      reconnectAttemptRef.current = nextAttempt;
      const delay = computeBackoffDelay(nextAttempt);

      if (reconnectTimeoutRef.current) {
        window.clearTimeout(reconnectTimeoutRef.current);
      }

      reconnectTimeoutRef.current = window.setTimeout(() => {
        connect();
      }, delay);
      setConnectionState('error');
    },
    [token],
  );

  /**
   * Fecha a conexão atual limpando timers associados.
   */
  const cleanupConnection = useCallback(() => {
    if (reconnectTimeoutRef.current) {
      window.clearTimeout(reconnectTimeoutRef.current);
      reconnectTimeoutRef.current = null;
    }

    const socket = websocketRef.current;
    if (socket) {
      socket.onclose = null;
      socket.onmessage = null;
      socket.onerror = null;
      socket.close();
    }

    websocketRef.current = null;
  }, []);

  /**
   * Estabelece conexão WebSocket autenticada com o backend.
   */
  const connect = useCallback(() => {
    if (!token || websocketRef.current) {
      return;
    }

    try {
      setConnectionState('connecting');
      const url = buildNotificationsWebSocketUrl(token);
      const socket = new WebSocket(url);
      websocketRef.current = socket;
      isManuallyClosedRef.current = false;

      socket.onopen = () => {
        reconnectAttemptRef.current = 0;
        setConnectionState('connected');
        syncChannelSubscriptions();
      };

      socket.onmessage = (event) => {
        handleMessage(event).catch((error) => {
          console.error('Erro ao processar mensagem do WebSocket.', error);
        });
      };

      socket.onerror = () => {
        setConnectionState('error');
      };

      socket.onclose = (event) => {
        websocketRef.current = null;
        setConnectionState('idle');
        scheduleReconnect(event);
      };
    } catch (error) {
      console.error('Falha ao conectar ao WebSocket de notificações.', error);
      scheduleReconnect();
    }
  }, [handleMessage, scheduleReconnect, syncChannelSubscriptions, token]);

  /**
   * Observa mudanças de autenticação para iniciar ou encerrar a conexão.
   */
  useEffect(() => {
    if (!token || !user) {
      isManuallyClosedRef.current = true;
      cleanupConnection();
      setConnectionState('idle');
      return;
    }

    connect();

    return () => {
      isManuallyClosedRef.current = true;
      cleanupConnection();
    };
  }, [cleanupConnection, connect, token, user]);

  /**
   * Garante que listeners sejam limpos quando o componente desmontar.
   */
  useEffect(() => {
    return () => {
      listenersRef.current.general.clear();
      listenersRef.current.byMonitored.clear();
      processedEventsRef.current.clear();
      activeMonitoredChannelsRef.current.clear();
    };
  }, []);

  /**
   * Inscreve listeners de forma segura evitando duplicidades.
   */
  const subscribe = useCallback((handler: NotificationEventHandler) => {
    listenersRef.current.general.add(handler);
    return () => {
      listenersRef.current.general.delete(handler);
    };
  }, []);

  /**
   * Inscreve handler associado a um monitorado específico enviando subscribe via WS.
   */
  const subscribeToMonitored = useCallback(
    (monitoredId: string, handler: NotificationEventHandler) => {
      const registry = listenersRef.current.byMonitored;
      const existing = registry.get(monitoredId) ?? new Set<NotificationEventHandler>();
      existing.add(handler);
      registry.set(monitoredId, existing);

      const counter = activeMonitoredChannelsRef.current.get(monitoredId) ?? 0;
      activeMonitoredChannelsRef.current.set(monitoredId, counter + 1);

      syncChannelSubscriptions();

      return () => {
        const listeners = registry.get(monitoredId);
        listeners?.delete(handler);

        if (listeners && listeners.size === 0) {
          registry.delete(monitoredId);
        }

        const currentCount = activeMonitoredChannelsRef.current.get(monitoredId) ?? 0;
        if (currentCount <= 1) {
          activeMonitoredChannelsRef.current.delete(monitoredId);
          const socket = websocketRef.current;
          if (socket && socket.readyState === WebSocket.OPEN) {
            socket.send(
              JSON.stringify({
                action: 'unsubscribe',
                channels: [`monitored:${monitoredId}`],
              }),
            );
          }
        } else {
          activeMonitoredChannelsRef.current.set(monitoredId, currentCount - 1);
        }
      };
    },
    [syncChannelSubscriptions],
  );

  const value = useMemo<NotificationsContextValue>(
    () => ({
      connectionState,
      isConnected: connectionState === 'connected',
      subscribe,
      subscribeToMonitored,
    }),
    [connectionState, subscribe, subscribeToMonitored],
  );

  return <NotificationsContext.Provider value={value}>{children}</NotificationsContext.Provider>;
};

/**
 * Hook utilitário para acessar o contexto de notificações e garantir disponibilidade.
 */
export const useNotificationsContext = (): NotificationsContextValue => {
  const context = useContext(NotificationsContext);
  if (!context) {
    throw new Error('useNotificationsContext deve ser usado dentro de NotificationsProvider.');
  }
  return context;
};
