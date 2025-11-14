/**
 * Cliente HTTP para comunicação com o backend market_alert
 *
 * Contém funções utilitárias para chamadas HTTP autenticadas e
 * tipos/contratos usados pelo frontend para consumir a API.
 */

/**
 * URL padrão usada quando nenhuma variável de ambiente é fornecida.
 */
const DEFAULT_API_URL = 'http://localhost:8000/';

/** Nome do evento emitido globalmente quando a sessão expira (401) */
export const SESSION_EXPIRED_EVENT = 'session-expired';

/**
 * Normaliza e valida a URL base da API informada via variável de ambiente.
 * 
 * - Remove espaços em branco acidentais
 * - Garante a presença de esquema/host válidos utilizando URL nativa do navegador
 * - Força o término com uma única barra para simplificar a concatenação de endpoints
 */
export const normalizeBaseApiUrl = (rawUrl?: string): string => {
  const trimmed = rawUrl?.trim();

  if (!trimmed) {
    return DEFAULT_API_URL;
  }

  try {
    const parsed = new URL(trimmed);
    // Limpa query/hash passados inadvertidamente
    parsed.search = '';
    parsed.hash = '';

    const normalizedPath = parsed.pathname.replace(/\/+$/, '');
    parsed.pathname = normalizedPath ? `${normalizedPath}/` : '/';

    return parsed.toString();
  } catch (error) {
    console.warn('URL base da API inválida, retornamos o fallback padrão.', error);
    return DEFAULT_API_URL;
  }
};

/**
 * Retorna a URL base da API (variável de ambiente Vite normalizada ou fallback).
 */
export const getApiUrl = () => normalizeBaseApiUrl(import.meta.env.VITE_FRONTEND_FORGE_API_URL);

/**
 * Monta a URL final da requisição garantindo que o endpoint tenha formato consistente.
 */
const buildApiUrl = (endpoint: string): string => {
  const sanitizedEndpoint = endpoint.startsWith('/') ? endpoint.slice(1) : endpoint;
  const base = getApiUrl();

  try {
    return new URL(sanitizedEndpoint, base).toString();
  } catch (error) {
    const normalizedBase = base.endsWith('/') ? base : `${base}/`;
    return `${normalizedBase}${sanitizedEndpoint}`;
  }
};

/**
 * Função auxiliar para fazer requisições HTTP com autenticação.
 *
 * - Aceita um token opcional que é colocado no header Authorization.
 * - Mantém compatibilidade com RequestInit do fetch (method, body, etc).
 * - Converte o body para JSON quando necessário (caller já envia JSON.stringify).
 * - Lança erro com mensagem padrão quando a resposta não for ok.
 */
export const apiRequest = async <T = any>(
  endpoint: string,
  options: RequestInit & { token?: string; timeoutMs?: number } = {},
): Promise<T> => {
  const { token, headers: requestHeaders, timeoutMs, signal: callerSignal, ...fetchOptions } = options;
  const url = buildApiUrl(endpoint);

  const headers = new Headers(requestHeaders as HeadersInit | undefined);

  if (!headers.has('Accept')) {
    headers.set('Accept', 'application/json');
  }

  const body = fetchOptions.body;
  const shouldSetJsonContentType =
    body !== undefined &&
    !headers.has('Content-Type') &&
    !(body instanceof FormData) &&
    !(body instanceof URLSearchParams) &&
    !(body instanceof Blob);

  if (shouldSetJsonContentType) {
    headers.set('Content-Type', 'application/json');
  }

  if (token) {
    // Utilizamos set para garantir que o header Authorization seja persistido no objeto Headers
    headers.set('Authorization', `Bearer ${token}`);
  }

  const controller = new AbortController();
  const timeout = typeof timeoutMs === 'number' ? timeoutMs : 15_000;

  if (callerSignal) {
    if (callerSignal.aborted) {
      controller.abort();
    } else {
      callerSignal.addEventListener('abort', () => controller.abort(), { once: true });
    }
  }

  const timeoutId = setTimeout(() => {
    controller.abort();
  }, timeout);

  let response: Response;

  try {
    response = await fetch(url, {
      ...fetchOptions,
      headers,
      signal: controller.signal,
    });
  } catch (error) {
    if (error instanceof Error && error.name === 'AbortError') {
      throw new Error('Tempo limite atingido. Verifique sua conexão e tente novamente.');
    }

    throw error;
  } finally {
    clearTimeout(timeoutId);
  }

  // Tratamento aprimorado de erro: prioriza mensagens do backend antes do fallback genérico
  if (!response.ok) {
    const prioritizedFields: Array<'detail' | 'message' | 'msg'> = ['detail', 'message', 'msg'];

    // Função recursiva para transformar qualquer estrutura em uma mensagem legível
    const toReadableMessage = (value: unknown): string | null => {
      if (value === null || value === undefined) {
        return null;
      }

      if (typeof value === 'string') {
        return value.trim() || null;
      }

      if (typeof value === 'number' || typeof value === 'boolean') {
        return String(value);
      }

      if (Array.isArray(value)) {
        const aggregated = value
          .map((item) => toReadableMessage(item))
          .filter((message): message is string => Boolean(message));

        return aggregated.length > 0 ? aggregated.join(' | '): null;
      }

      if (typeof value === 'object') {
        const record = value as Record<string, unknown>;

        for (const field of prioritizedFields) {
          if (field in record) {
            const nested = toReadableMessage(record[field]);

            if (nested) {
              return nested;
            }
          }
        }

        const fallbackMessages = Object.values(record)
          .map((item) => toReadableMessage(item))
          .filter((message): message is string => Boolean(message));

        return fallbackMessages.length > 0 ? fallbackMessages.join(' | ') : null;
      }

      return null;
    };

    let parsedBody: unknown = null;

    try {
      // Clonamos a resposta para evitar perder o body caso não seja JSON
      parsedBody = await response.clone().json();
    } catch (error) {
      // Manteremos parsedBody como null quando backend não retornar JSON
      parsedBody = null;
    }

    let extractedMessage: string | null = null;

    if (parsedBody && typeof parsedBody === 'object' && !Array.isArray(parsedBody)) {
      const bodyRecord = parsedBody as Record<string, unknown>;

      for (const field of prioritizedFields) {
        if (field in bodyRecord) {
          extractedMessage = toReadableMessage(bodyRecord[field]);

          if (extractedMessage) {
            break;
          }
        }
      }

      if (!extractedMessage) {
        extractedMessage = toReadableMessage(bodyRecord);
      }
    } else {
      extractedMessage = toReadableMessage(parsedBody);
    }

    if (!extractedMessage) {
      try {
        const textBody = await response.text();
        extractedMessage = textBody.trim() || null;
      } catch (error) {
        // Se nem texto conseguir obter, mantem fallback genérico
        extractedMessage = null;
      }
    }

    if (token && response.status === 401 && typeof window !== 'undefined') {
      window.dispatchEvent(new CustomEvent(SESSION_EXPIRED_EVENT));
    }

    const message =
      extractedMessage || (response.status === 401 ? 'Sessão expirada' : `Erro ${response.status}`);

    // Ao lançar a exceção, garantimos que a mensagem reflita o conteúdo retornado pelo backend
    throw new Error(message);
  }

  // Deserializa o corpo JSON da resposta
  return response.json();
};

/**
 * Estrutura da resposta de autenticação que contém o token JWT.
 */
interface AuthResponse {
  access_token: string;
  token_type: string;
}

/**
 * Realiza login no backend enviando credenciais em formato form-urlencoded.
 * 
 * A função utiliza apiRequest para reaproveitar o tratamento de erros centralizado,
 * garantindo que mensagens vindas do backend (como detail) sejam preservadas.
 */
export const login = async (email: string, password: string): Promise<string> => {
  // Utilizamos URLSearchParams para garantir a codificação correta dos campos de fomulário
  const body = new URLSearchParams({
    username: email,
    password: password,
  });

  const response = await apiRequest<AuthResponse>('/auth/', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/x-www-form-urlencoded',
    },
    // toString assegura que o corpo seja enviado como string, respeitando o content-type configurado
    body: body.toString(),
  });

  return response.access_token;
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
  potential_savings?: string | number | null;
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
  potential_savings: number | null;
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
  potential_savings?: string | number | null;
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
  potential_savings?: string | number | null;
  comparison_insights: string | null;
  comparison_id?: string | null;
  last_comparison_at?: string | null;
}

/**
 * Converte valores decimais/strings em números ou null quando invalido.
 */
const toNumberOrNull = (value: string | number | null | undefined): number | null => {
  if (value === null || value === undefined) {
    return null;
  }

  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : null;
};

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
  potential_savings: toNumberOrNull(product.potential_savings),
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
    potential_savings: toNumberOrNull(summary.potential_savings),
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

interface PaginatedCompetitorsApiResponse {
  items: CompetitorListItemApiResponse[];
  total: number;
  page: number;
  per_page: number;
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

  const data = await apiRequest<PaginatedResponse<MonitoredProductApiResponse>>(endpoint, { token });
  return {
    ...data,
    items: data.items.map(mapMonitoredProductFromApi),
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

  const data = await apiRequest<PaginatedCompetitorsApiResponse>(`/competitors?${searchParams.toString()}`, {
    token,
  });

  return {
    items: data.items.map(mapCompetitorFromApi),
    total: data.total,
    page: data.page,
    per_page: data.per_page,
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
 * 
 * - Aceita cabeçalho Idempotency-Key para evitar duplicações em cliques repetidos.
 * - Quando nenhuma chave for informada, geramos uma automaticamente.
 */
export const scrapeCompetitor = (
  token: string,
  data: {
    monitored_product_id: string;
    product_url: string;
  },
  options: {
    idempotencyKey?: string;
  } = {},
) => {
  const resolvedIdempotencyKey = (() => {
    if (options.idempotencyKey) {
      return options.idempotencyKey;
    }

    if (typeof crypto !== 'undefined' && 'randomUUID' in crypto) {
      return crypto.randomUUID();
    }

    return `${Date.now()}-${Math.random().toString(36).slice(2)}`;
  })();

  return apiRequest<{ message: string }>('/competitors/scrape', {
    token,
    method: 'POST',
    body: JSON.stringify(data),
    headers: {
      'Idempotency-Key': resolvedIdempotencyKey,
    },
  });
};

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
 * POST /comparisons/{monitoredId}/run?tolerance=...&price_change_threshold=...
 *
 * - tolerance: tolerância para considerar preços equivalentes (opcional)
 * - priceChangeThreshold: limiar para considerar variação significativa (opcional)
 */
export const runComparison = (
  token: string,
  monitoredId: string,
  tolerance?: number,
  priceChangeThreshold?: number,
) => {
  const payload: Record<string, number> = {};

  if (tolerance !== undefined) {
    payload.tolerance = tolerance;
  }

  if (priceChangeThreshold !== undefined) {
    payload.price_change_threshold = priceChangeThreshold;
  }

  const hasCustomParameters = Object.keys(payload).length > 0;

  return apiRequest<PriceComparison>(`/comparisons/${monitoredId}/run`, {
    token,
    method: 'POST',
    ...(hasCustomParameters
      ? {
          body: JSON.stringify(payload),
          headers: {
            // Evitamos envio desnecessário quando não há tolerâncias para preservar contratos antigos.
            'Content-Type': 'application/json',
          },
        }
      : {}),
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
    potential_savings: number;
  }>('/dashboard/stats', { token });
