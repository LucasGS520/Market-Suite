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
  options: RequestInit & { token?: string } = {}
): Promise<T> => {
  const { token, headers: requestHeaders, ...fetchOptions } = options;
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

  const response = await fetch(url, {
    ...fetchOptions,
    headers,
  });

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

    const message = extractedMessage || `Erro ${response.status}`;

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
  competitors_count?: number | null;
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
}

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
  competitors_count: product.competitors_count !== undefined && product.competitors_count !== null ? toNumberOrNull(product.competitors_count) : undefined,
});

/**
 * Interface para concorrente (Competitor).
 * Representa um produto similar cadastrado como concorrente de um monitorado.
 */
export interface Competitor {
  id: string;
  monitored_product_id: string;
  name_competitor: string;
  product_url: string;
  current_price: string | number | null;
  old_price?: string | number | null;
  free_shipping?: boolean | null;
  seller?: string | null;
  seller_rating?: number | null;
  thumbnail?: string | null;
  status: 'available' | 'unavailable' | 'removed';
  last_checked?: string | null;
  created_at?: string | null;
  updated_at?: string | null;
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
  pct_x_target: number | null;
  pct_x_monitored: number | null;
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
  pct_below_target?: number;
  old_price?: number;
  change?: number;
  pct_change?: number | null;
  type?: 'price_increase' | 'price_decrease';
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
 * API: Listar produtos monitorados do usuário.
 * GET /monitored
 */
export const getMonitoredProducts = async (token: string): Promise<MonitoredProduct[]> => {
  const data = await apiRequest<MonitoredProductApiResponse[]>('/monitored', { token });
  return data.map(mapMonitoredProductFromApi);
};

/**
 * API: Agendar scraping de produto monitorado (coleta imediata via backend).
 * POST /monitored/scrape
 */
export const scrapeMonitoredProduct = (
  token: string,
  data: {
    name_identification: string;
    product_url: string;
  }
) =>
  apiRequest<{ message: string }>('/monitored/scrape', {
    token,
    method: 'POST',
    body: JSON.stringify(data),
  });

/**
 * API: Listar concorrentes de um produto monitorado.
 * GET /competitors/{monitoredProductId}
 */
export const getCompetitors = (token: string, monitoredProductId: string) =>
  apiRequest<Competitor[]>(`/competitors/${monitoredProductId}`, { token });

/**
 * API: Agendar scraping de concorrente.
 * POST /competitors/scrape
 */
export const scrapeCompetitor = (
  token: string,
  data: {
    monitored_product_id: string;
    product_url: string;
  }
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
  priceChangeThreshold?: number
) => {
  const params = new URLSearchParams();
  if (tolerance !== undefined) params.append('tolerance', tolerance.toString());
  if (priceChangeThreshold !== undefined) params.append('price_change_threshold', priceChangeThreshold.toString());

  return apiRequest<PriceComparison>(`/comparisons/${monitoredId}/run?${params}`, {
    token,
    method: 'POST',
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
