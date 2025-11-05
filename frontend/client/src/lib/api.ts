/**
 * Cliente HTTP para comunicação com o backend market_alert
 *
 * Contém funções utilitárias para chamadas HTTP autenticadas e
 * tipos/contratos usados pelo frontend para consumir a API.
 */

import Products from "@/pages/Products";

/**
 * Retorna a URL base da API (variável de ambiente Vite ou fallback).
 */
const getApiUrl = () => {
  // import.meta.env é injetado pelo Vite em tempo de build
  return import.meta.env.VITE_FRONTEND_FORGE_API_URL || 'http://localhost:8000';
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
  const { token, ...fetchOptions } = options;
  const url = `${getApiUrl()}${endpoint}`;

  // Cabeçalhos padrão para enviar/receber JSON
  const headers: HeadersInit = {
    'Content-Type': 'application/json',
  };

  // Mescla headers passados via fetchOptions (se houver)
  if (fetchOptions.headers) {
    Object.assign(headers, fetchOptions.headers);
  }

  // Adiciona token no Authorization quando fornecido
  if (token) {
    Object.assign(headers, { Authorization: `Bearer ${token}` });
  }

  // Executa a requisição usando fetch padrão do navegador
  const response = await fetch(url, {
    ...fetchOptions,
    headers,
  });

  // Tratamento simples de erro: tenta extrair mensagem JSON, fallback para genérico
  if (!response.ok) {
    const error = await response.json().catch(() => ({ message: 'Erro desconhecido' }));
    throw new Error(error.message || `Erro ${response.status}`);
  }

  // Deserializa o corpo JSON da resposta
  return response.json();
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
  target_price: string | number;
  current_price: string | number;
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
  target_price: number | null;
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
  target_price: toNumberOrNull(product.target_price),
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
 * Interface para resultado de comparação de preços (PriceComparison).
 * Agrega preços do monitorado e dos concorrentes e lista alertas decorrentes.
 */
export interface PriceComparison {
  monitored_product_id: string;
  monitored_price: number;
  competitors_prices: number[];
  average_competitor_price: number;
  price_difference: number;
  price_difference_percentage: number;
  alerts: Alert[];
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
 * API: Criar novo produto monitorado.
 * POST /monitored
 * Body esperado: { name_identification, product_url, target_price }
 */
export const createMonitoredProduct = async (
  token: string,
  data: {
    name_identification: string;
    product_url: string;
    target_price: number;
  }
): Promise<MonitoredProduct> => {
  const response = await apiRequest<MonitoredProductApiResponse>('/monitored', {
    token,
    method: 'POST',
    body: JSON.stringify(data),
  });

  return mapMonitoredProductFromApi(response);
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
    target_price: number;
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
 * API: Adicionar concorrente a um monitorado.
 * POST /competitors
 * Body esperado: { monitored_product_id, product_url }
 */
export const addCompetitor = (
  token: string,
  data: {
    monitored_product_id: string;
    product_url: string;
  }
) =>
  apiRequest<Competitor>('/competitors', {
    token,
    method: 'POST',
    body: JSON.stringify(data),
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
