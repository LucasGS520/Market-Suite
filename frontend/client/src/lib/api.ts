import axios, { type AxiosRequestConfig } from 'axios';
import {
  ACCESS_TOKEN_STORAGE_KEY,
  REFRESH_TOKEN_STORAGE_KEY,
  SESSION_EXPIRED_EVENT,
  TOKENS_REFRESHED_EVENT,
  clearStoredTokens,
  getStoredAccessToken,
  getStoredRefreshToken,
  persistTokens,
} from './auth/storage';
import {
  apiClient,
  extractErrorMessage,
  normalizePaginated,
  type PaginatedPayload,
} from './http/client';
import { parseMoneyValue } from './money';

export {
  SESSION_EXPIRED_EVENT,
  TOKENS_REFRESHED_EVENT,
  clearStoredTokens,
  getStoredAccessToken,
  getStoredRefreshToken,
  persistTokens,
} from './auth/storage';

/**
 * Cliente HTTP para comunicação com o backend market_alert
 *
 * Contém funções utilitárias para chamadas HTTP autenticadas e
 * tipos/contratos usados pelo frontend para consumir a API.
 */

/**
 * Decodifica o payload de um JWT retornando objeto plano.
 *
 * Usado apenas para verificar validade local do token e evitar reconexões com credenciais expiradas.
 */
export const decodeJwtPayload = (token: string): Record<string, unknown> | null => {
  try {
    const [, payload] = token.split('.');
    const normalized = payload.replace(/-/g, '+').replace(/_/g, '/');
    const decoded = atob(normalized);
    return JSON.parse(decoded);
  } catch (error) {
    console.warn('Não foi possível decodificar o token JWT.', error);
    return null;
  }
};

/**
 * Verifica se o token já expirou ou expira em breve.
 */
export const isTokenExpired = (token: string, leewaySeconds = 60): boolean => {
  const payload = decodeJwtPayload(token);
  const exp = typeof payload?.exp === 'number' ? payload.exp : null;

  if (!exp) {
    return false;
  }

  const nowSeconds = Math.floor(Date.now() / 1000);
  return nowSeconds >= exp - leewaySeconds;
};

/** Estrutura de resposta contendo par de tokens de autenticação. */
export interface TokenPairResponse {
  access_token: string;
  refresh_token: string;
  token_type: string;
}

/** Atualiza caches locais e notifica listeners globais sobre novos tokens. */
const persistAndBroadcastTokens = (tokenPair: TokenPairResponse): void => {
  persistTokens(tokenPair.access_token, tokenPair.refresh_token);

  if (typeof window !== 'undefined') {
    window.dispatchEvent(new CustomEvent(TOKENS_REFRESHED_EVENT, { detail: tokenPair }));
  }
};

/** Solicita novos tokens utilizando refresh token bruto. */
const requestTokenRefresh = async (refreshToken: string): Promise<TokenPairResponse> => {
  const response = await apiClient.post<TokenPairResponse>('/auth/refresh', {
    refresh_token: refreshToken,
  });

  return response.data;
};

/**
 * Função auxiliar para fazer requisições HTTP com autenticação.
 *
 * - Aceita um token opcional que é colocado no header Authorization.
 * - Adiciona timeout padrão e converte erros para mensagens legíveis.
 */
export interface ApiRequestOptions extends AxiosRequestConfig {
  token?: string;
  timeoutMs?: number;
  retryOnAuthFailure?: boolean;
  allowAuthRefresh?: boolean;
  body?: unknown;
}

export const apiRequest = async <T = any>(
  endpoint: string,
  options: ApiRequestOptions = {},
): Promise<T> => {
  const { token, timeoutMs, retryOnAuthFailure = true, allowAuthRefresh = true, ...axiosOptions } = options;
  const effectiveToken = token ?? getStoredAccessToken();
  let dispatchedSessionExpiration = false;

  const performAuthRefresh = async (): Promise<TokenPairResponse | null> => {
    const refreshToken = getStoredRefreshToken();
    if (!refreshToken || !allowAuthRefresh) {
      return null;
    }

    try {
      const refreshed = await requestTokenRefresh(refreshToken);
      persistAndBroadcastTokens(refreshed);
      return refreshed;
    } catch (error) {
      clearStoredTokens();
      if (typeof window !== 'undefined') {
        dispatchedSessionExpiration = true;
        window.dispatchEvent(new CustomEvent(SESSION_EXPIRED_EVENT));
      }
      console.error('Falha ao renovar sessão de forma silenciosa.', error);
      return null;
    }
  };

  const headers: AxiosRequestConfig['headers'] = {
    Accept: 'application/json',
    ...(axiosOptions.headers ?? {}),
  }; 

  if (effectiveToken && !(headers && 'Authorization' in headers)) {
    (headers as Record<string, string>).Authorization = `Bearer ${effectiveToken}`;
  }

  const timeout = timeoutMs ?? axiosOptions.timeout ?? 15_000;
  const { body, data, ...requestOptions } = axiosOptions as AxiosRequestConfig & {
    body?: unknown;
  };
  const payload = data ?? body;

  try {
    const response = await apiClient.request<T>({
      url: endpoint,
      ...requestOptions,
      data: payload,
      headers,
      timeout,
    });

    return response.data;
  } catch (error) {
    const axiosError = axios.isAxiosError(error) ? error : null;

    if (axiosError) {
      if (axiosError.code === 'ECONNABORTED') {
        throw new Error('Tempo limite atingido. Verifique sua conexão e tente novamente.');
      }

      const status = axiosError.response?.status;
      const isAuthFailure = status === 401 || status === 403;

      if (isAuthFailure && retryOnAuthFailure && effectiveToken) {
        const refreshed = await performAuthRefresh();
        if (refreshed) {
          return apiRequest<T>(endpoint, {
            ...options,
            token: refreshed.access_token,
            retryOnAuthFailure: false,
            allowAuthRefresh,
          });
        }
      }

      if (effectiveToken && status === 401 && typeof window !== 'undefined' && !dispatchedSessionExpiration) {
        window.dispatchEvent(new CustomEvent(SESSION_EXPIRED_EVENT));
      }

      throw new Error(extractErrorMessage(axiosError));
    }

    if (error instanceof Error && error.name === 'CanceledError') {
      throw new Error('Tempo limite atingido. Verifique sua conexão e tente novamente.');
    }

    throw new Error(extractErrorMessage(error));
  }
};

/**
 * Realiza login no backend enviando credenciais em formato form-urlencoded.
 * 
 * A função utiliza apiRequest para reaproveitar o tratamento de erros centralizado,
 * garantindo que mensagens vindas do backend (como detail) sejam preservadas.
 */
export const login = async (email: string, password: string): Promise<TokenPairResponse> => {
  // Utilizamos URLSearchParams para garantir a codificação correta dos campos de fomulário
  const body = new URLSearchParams({
    username: email,
    password: password,
  });

  const response = await apiRequest<TokenPairResponse>('/auth/', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/x-www-form-urlencoded',
    },
    // toString assegura que o corpo seja enviado como string, respeitando o content-type configurado
    body: body.toString(),
    retryOnAuthFailure: false,
    allowAuthRefresh: false,
  });

  persistAndBroadcastTokens(response);

  return response;
};

/**
 * Realiza refresh explícito (útil em fluxos de reconexão ou interceptores).
 */
export const refreshTokens = async (refreshToken: string): Promise<TokenPairResponse> => {
  const refreshed = await requestTokenRefresh(refreshToken);
  persistAndBroadcastTokens(refreshed);
  return refreshed;
};

/**
 * Interface para resposta paginada genérica.
 * - items: lista de itens da página
 * - total: total de itens disponíveis
 * - page: página atual (base 1)
 * - per_page: itens por página
 */
export interface PaginatedResponse<T> {
  items: T[];
  total: number;
  page: number;
  per_page: number;
}

/**
 * Interface para produto monitorado (MonitoredProduct).
 * Representa um item que o usuário deseja monitorar preços.
 */
/**
 * Estrutura textual retornada pelo backend para indicar o estado de um produto monitorado.
 */
export type MonitoredStatus = 'active' | 'inactive' | 'pending' | 'failed';

/**
 * Estrutura extra recebida o backend para produtos monitorados (snake_case e Decimals em string).
 */
export interface MonitoredProductApiResponse {
  id: string;
  user_id: string;
  name_identification?: string | null;
  monitoring_type: 'api' | 'scraping';
  search_query?: string | null;
  product_url?: string | null;
  current_price?: string | number | null;
  free_shipping?: boolean | null;
  thumbnail?: string | null;
  status: MonitoredStatus;
  last_checked?: string | null;
  competitors_count?: number | string | null;
  competitors_mean?: string | number | null;
  competitors_min?: string | number | null;
  competitors_max?: string | number | null;
  position_rank?: number | string | null;
  potential_adjustment?: string | number | null;
  competitors_with_price_count?: number | string | null;
  latest_comparison_id?: string | null;
  last_comparison_at?: string | null;
  is_new?: boolean | null;
  comparison_insights?: string | null;
}

/**
 * Interface utilizada pelo frontend após normalizar tipos numéricos e opcionais da API
 */
export interface MonitoredProduct {
  id: string;
  user_id: string;
  name_identification: string | null;
  monitoring_type: 'api' | 'scraping';
  search_query: string | null;
  product_url: string | null;
  current_price: number | null;
  free_shipping: boolean | null;
  thumbnail: string | null;
  status: MonitoredStatus;
  last_checked: string | null;
  competitors_count: number | null;
  competitors_mean: number | null;
  competitors_min: number | null;
  competitors_max: number | null;
  position_rank: number | null;
  potential_adjustment: number | null;
  competitors_with_price_count: number | null;
  latest_comparison_id: string | null;
  last_comparison_at: string | null;
  is_new: boolean;
  comparison_insights: string | null;
}

/**
 * Estrutura bruta do resumo competitivo retornado pelo backend.
 * 
 * Mantém campos novos (contract card-first) e legados para garantir compatibilidade durante a transição do backend.
 */
export interface ComparisonSummaryApiResponse {
  monitored_price?: string | number | null;
  competitors_count?: number | string | null;
  competitors_with_price_count?: number | string | null;
  competitors_mean?: string | number | null;
  competitors_min?: string | number | null;
  competitors_max?: string | number | null;
  potential_adjustment?: string | number | null;
  comparison_id?: string | null;
  last_comparison_at?: string | null;
  comparison_insights?: string | null;
  position_rank?: string | number | null;
  
  /** Campos legados preservados para retrocompatibilidade de deploy. */
  average_competitor_price?: string | number | null;
  min_competitor_price?: string | number | null;
  max_competitor_price?: string | number | null;
}

/**
 * Estrutura normalizada do resumo competitivo consumido pelo frontend.
 */
export interface ComparisonSummary {
  monitored_price?: string | number | null;
  competitors_count?: number | string | null;
  competitors_with_price_count?: number | string | null;
  competitors_mean?: string | number | null;
  competitors_min?: string | number | null;
  competitors_max?: string | number | null;
  position_rank: number | null;
  potential_adjustment?: string | number | null;
  comparison_insights: string | null;
  comparison_id?: string | null;
  last_comparison_at?: string | null;
}

/**
 * Converte valores decimais/strings em números ou null utilizando Decimal para precisão.
 */
const toNumberOrNull = (value: string | number | null | undefined): number | null =>
  parseMoneyValue(value);

/**
 * Normaliza o payload recebido da API para o formato consumido na UI 
 */
export const mapMonitoredProductFromApi = (
  product: MonitoredProductApiResponse,
): MonitoredProduct => ({
  id: product.id,
  user_id: product.user_id,
  name_identification: product.name_identification ?? null,
  monitoring_type: product.monitoring_type,
  search_query: product.search_query ?? null,
  product_url: product.product_url ?? null,
  current_price: toNumberOrNull(product.current_price),
  free_shipping: product.free_shipping ?? null,
  thumbnail: product.thumbnail ?? null,
  status: product.status,
  last_checked: product.last_checked ?? null,
  competitors_count:
    product.competitors_count !== undefined && product.competitors_count !== null
      ? toNumberOrNull(product.competitors_count)
      : null,
  competitors_mean: toNumberOrNull(product.competitors_mean),
  competitors_min: toNumberOrNull(product.competitors_min),
  competitors_max: toNumberOrNull(product.competitors_max),
  position_rank: toNumberOrNull(product.position_rank),
  potential_adjustment: toNumberOrNull(product.potential_adjustment),
  competitors_with_price_count:
    product.competitors_with_price_count !== undefined && product.competitors_with_price_count !== null
      ? toNumberOrNull(product.competitors_with_price_count)
      : null,
  latest_comparison_id: product.latest_comparison_id ?? null,
  last_comparison_at: product.last_comparison_at ?? null,
  is_new: Boolean(product.is_new),
  comparison_insights: product.comparison_insights ?? null,
});

/**
 * Normaliza o resumo competitivo retornado pelo backend.
 */
const mapComparisonSummaryFromApi = (
  summary: ComparisonSummaryApiResponse,
): ComparisonSummary => {
  /**
   * Campos de preço mantêm fallback para nomenclaturas antigas evitando que cartões
   * fiquem vazios durante rollout parcial do backend.
   */
  const meanSource = summary.competitors_mean ?? summary.average_competitor_price;
  const minSource = summary.competitors_min ?? summary.min_competitor_price;
  const maxSource = summary.competitors_max ?? summary.max_competitor_price;

  return {
    monitored_price: toNumberOrNull(summary.monitored_price),
    competitors_count:
      summary.competitors_count !== undefined && summary.competitors_count !== null
        ? Number(toNumberOrNull(summary.competitors_count)) || 0
        : 0,
    competitors_with_price_count:
      summary.competitors_with_price_count !== undefined && summary.competitors_with_price_count !== null
        ? Number(toNumberOrNull(summary.competitors_with_price_count)) || 0
        : 0,
    competitors_mean: toNumberOrNull(meanSource),
    competitors_min: toNumberOrNull(minSource),
    competitors_max: toNumberOrNull(maxSource),
    position_rank: toNumberOrNull(summary.position_rank),
    potential_adjustment: toNumberOrNull(summary.potential_adjustment),
    comparison_insights: summary.comparison_insights ?? null,
    comparison_id: summary.comparison_id ?? null,
    last_comparison_at: summary.last_comparison_at ?? null,
  };
};

/**
 * Interface para concorrente na listagem card-first.
 * Mantém números já convertidos para facilitar cálculos na camada de UI.
 */
export interface Competitor {
  id: string;
  monitored_product_id: string;
  name: string;
  product_url: string;
  current_price: number | null;
  previous_price: number | null;
  price_change: number | null;
  price_change_percentage: number | null;
  status: 'available' | 'unavailable' | 'removed';
  last_checked: string | null;
  is_paused: boolean;
}

/**
 * Parâmetros aceitos pela listagem paginada de concorrentes.
 */
export interface CompetitorQueryParams {
  page?: number;
  per_page?: number;
  search?: string;
  status?: Competitor['status'];
  include_paused?: boolean;
  sort_by?: 'price' | 'last_checked' | 'price_change';
  sort_direction?: 'asc' | 'desc';
}

/**
 * Resposta paginada de concorrentes convertida para tipos amigáveis.
 */
export interface PaginatedCompetitors {
  items: Competitor[];
  total: number;
  page: number;
  per_page: number;
}

/**
 * Payload padrão para ações em massa sobre concorrentes.
 */
export interface CompetitorBulkActionPayload {
  monitored_product_id: string;
  competitor_ids: string[];
}

/**
 * Estrutura de retorno das ações em massa executadas pelo backend.
 */
export interface CompetitorBulkActionResult {
  processed_ids: string[];
  skipped_ids: string[];
  total_processed: number;
}

/**
 * Estrutura bruta retornada pelo backend para cada concorrente da listagem.
 */
interface CompetitorListItemApiResponse {
  id: string;
  monitored_product_id: string;
  name: string;
  product_url: string;
  current_price: string | number | null;
  previous_price: string | number | null;
  price_change: string | number | null;
  price_change_percentage: string | number | null;
  status: Competitor['status'];
  last_checked: string | null;
  is_paused: boolean;
}

/**
 * Interface de notificação (Alert) conforme NotificationLogResponse do backend.
 * Representa cada tentativa de envio de alerta registrada, incluindo metadados do canal e status.
 */
export interface Alert {
  id: string;
  user_id: string;
  alert_rule_id?: string | null;
  alert_type?: string | null;
  channel: string;
  subject: string;
  message: string;
  provider_metadata?: Record<string, unknown> | null;
  sent_at: string;
  success: boolean;
  error?: string | null;
}

/**
 * Estrutura da discrepância por concorrente retornada pelo backend.
 * Mantém campos monetários e percentuais para cálculos em UI.
 */
export interface PriceDiscrepancy {
  competitor_id: string;
  name: string;
  price: number;
  pct_x_monitored: number | null;
  pct_below_monitored: number | null;
  delta_x_min_competitor: number;
  delta_x_monitored: number;
  old_price: number | null;
  change_from_old: number | null;
  pct_change_from_old: number | null;
}

/**
 * Estrutura de alertas retornada pela comparação de preços.
 * Os campos são opcionais porque variam conforme o tipo de alerta emitido.
 */
export interface PriceComparisonAlert {
  competitor_id?: string;
  product_id?: string;
  name?: string;
  status?: 'unavailable' | 'removed';
  price?: number;
  delta_x_monitored?: number | null;
  pct_below_monitored?: number | null;
  old_price?: number;
  change?: number;
  pct_change?: number | null;
  type?: 'price_event' | 'price_increase' | 'price_decrease';
}

/**
 * Interface para resultado de comparação de preços (PriceComparison).
 * Reflete fielmente os campos emitidos pelo endpoint `/comparisons/{id}run`.
 */
export interface PriceComparison {
  monitored_price: number;
  average_competitor_price: number | null;
  lowest_competitor: PriceDiscrepancy | null;
  highest_competitor: PriceDiscrepancy | null;
  discrepancies: PriceDiscrepancy[];
  alerts: PriceComparisonAlert[];
}

/**
 * Parâmetros aceitos na listagem de produtos monitorados.
 */
export interface MonitoredProductsQueryParams {
  page?: number;
  per_page?: number;
}

/**
 * Resposta paginada padronizada para produtos monitorados.
 */
export type PaginatedMonitoredProducts = PaginatedResponse<MonitoredProduct>;

/**
 * API: Listar produtos monitorados do usuário.
 * GET /monitored
 */
export const getMonitoredProducts = async (
  token: string,
  params?: MonitoredProductsQueryParams,
): Promise<PaginatedMonitoredProducts> => {
  const searchParams = new URLSearchParams();

  if (params?.page) {
    searchParams.set('page', params.page.toString());
  }

  if (params?.per_page) {
    searchParams.set('per_page', params.per_page.toString());
  }

  const queryString = searchParams.toString();
  const endpoint = queryString ? `/monitored?${queryString}` : '/monitored';

  const data = await apiRequest<PaginatedPayload<MonitoredProductApiResponse>>(endpoint, { token });
  const normalized = normalizePaginated(data);
  return {
    ...normalized,
    items: normalized.items.map(mapMonitoredProductFromApi),
  };
};

/**
 * API: Obter detalhes de um produto monitorado pelo ID.
 * GET /monitored/{id}
 */
export const getMonitoredProduct = async (token: string, id: string): Promise<MonitoredProduct> => {
  const data = await apiRequest<MonitoredProductApiResponse>(`/monitored/${id}`, { token });
  return mapMonitoredProductFromApi(data);
};

/**
 * API: Agendar scraping de produto monitorado (coleta imediata via backend).
 * POST /monitored/scrape
 */
export const scrapeMonitoredProduct = (
  token: string,
  data: {
    name_identification: string | null;
    product_url: string;
  }
) =>
  apiRequest<{ message: string }>('/monitored/scrape', {
    token,
    method: 'POST',
    body: JSON.stringify(data),
  });

/**
 * Converte um item bruto de concorrente em estrutura amigável para UI.
 */
const mapCompetitorFromApi = (item: CompetitorListItemApiResponse): Competitor => ({
  id: item.id,
  monitored_product_id: item.monitored_product_id,
  name: item.name,
  product_url: item.product_url,
  current_price: toNumberOrNull(item.current_price),
  previous_price: toNumberOrNull(item.previous_price),
  price_change: toNumberOrNull(item.price_change),
  price_change_percentage: toNumberOrNull(item.price_change_percentage),
  status: item.status,
  last_checked: item.last_checked,
  is_paused: item.is_paused,
});

/**
 * API: Listar concorrentes de um produto monitorado com filtros e paginação.
 * GET /competitors?monitored_id=...
 */
export const getCompetitors = async (
  token: string,
  monitoredProductId: string,
  params?: CompetitorQueryParams,
): Promise<PaginatedCompetitors> => {
  const searchParams = new URLSearchParams();
  searchParams.set('monitored_id', monitoredProductId);

  if (params?.page) searchParams.set('page', params.page.toString());
  if (params?.per_page) searchParams.set('per_page', params.per_page.toString());
  if (params?.search) searchParams.set('search', params.search);
  if (params?.status) searchParams.set('status', params.status);
  if (params?.include_paused !== undefined) searchParams.set('include_paused', String(params.include_paused));
  if (params?.sort_by) searchParams.set('sort_by', params.sort_by);
  if (params?.sort_direction) searchParams.set('sort_direction', params.sort_direction);

  const data = await apiRequest<PaginatedPayload<CompetitorListItemApiResponse>>(
    `/competitors?${searchParams.toString()}`,
    {
      token,
    },
  );
  const normalized = normalizePaginated(data);

  return {
    ...normalized,
    items: normalized.items.map(mapCompetitorFromApi),
  };
};

/**
 * API: Pausar concorrentes selecionados.
 */
export const pauseCompetitors = (
  token: string,
  payload: CompetitorBulkActionPayload,
): Promise<CompetitorBulkActionResult> =>
  apiRequest<CompetitorBulkActionResult>('/competitors/bulk/pause', {
    token,
    method: 'POST',
    body: JSON.stringify(payload),
  });

/**
 * API: Retomar concorrentes selecionados.
 */
export const resumeCompetitors = (
  token: string,
  payload: CompetitorBulkActionPayload,
): Promise<CompetitorBulkActionResult> =>
  apiRequest<CompetitorBulkActionResult>('/competitors/bulk/resume', {
    token,
    method: 'POST',
    body: JSON.stringify(payload),
  });

/**
 * API: Remover concorrentes selecionados.
 */
export const removeCompetitors = (
  token: string,
  payload: CompetitorBulkActionPayload,
): Promise<CompetitorBulkActionResult> =>
  apiRequest<CompetitorBulkActionResult>('/competitors/bulk/remove', {
    token,
    method: 'POST',
    body: JSON.stringify(payload),
  });

/**
 * API: Agendar scraping de concorrente.
 * POST /competitors/scrape
 */
export const scrapeCompetitor = (
  token: string,
  data: {
    monitored_product_id: string;
    product_url: string;
  },
) =>
  apiRequest<{ message: string }>('/competitors/scrape', {
    token,
    method: 'POST',
    body: JSON.stringify(data),
  });

/**
 * API: Listar logs de notificações do usuário.
 * GET /notifications/logs
 */
export const getAlerts = (token: string) =>
  apiRequest<Alert[]>('/notifications/logs', { token });

/**
 * API: Obter resumo competitivo quando dados agregados não vierem no monitorado.
 * GET /comparisons/{monitoredId}/summary
 */
export const getComparisonSummary = async (
  token: string,
  monitoredId: string,
): Promise<ComparisonSummary> => {
  const response = await apiRequest<ComparisonSummaryApiResponse>(
    `/comparisons/${monitoredId}/summary`,
    { token },
  );

  return mapComparisonSummaryFromApi(response);
};

/**
 * API: Rodar comparação de preços manualmente.
 * POST /comparisons/{monitoredId}/run?tolerance=...
 *
 * - tolerance: tolerância para considerar preços equivalentes (opcional)
 */
/**
 * Parâmetros opcionais aceitos ao acionar comparação manual.
 */
export interface RunComparisonOptions {
  tolerance?: number;
}

/**
 * API: Rodar comparação de preços manualmente com suporte a idempotência.
 */
export const runComparison = (
  token: string,
  monitoredId: string,
  options: RunComparisonOptions = {},
) => {
  const payload: Record<string, number> = {};

  if (options.tolerance !== undefined) {
    payload.tolerance = options.tolerance;
  }

  const hasCustomParameters = Object.keys(payload).length > 0;

  return apiRequest<PriceComparison>(`/comparisons/${monitoredId}/run`, {
    token,
    method: 'POST',
    ...(hasCustomParameters ? { body: JSON.stringify(payload) } : {}),
  });
};

/**
 * API: Obter estatísticas para o dashboard.
 * GET /dashboard/stats
 * Retorna contadores e métricas simples para resumo.
 */
export const getDashboardStats = (token: string) =>
  apiRequest<{
    total_monitored: number;
    active_alerts: number;
    ok_prices: number;
    potential_adjustment: number;
  }>('/dashboard/stats', { token });
