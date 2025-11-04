/**
 * Cliente HTTP para comunicação com o backend market_alert
 */

const getApiUrl = () => {
  return import.meta.env.VITE_FRONTEND_FORGE_API_URL || 'http://localhost:8000';
};

/**
 * Função auxiliar para fazer requisições HTTP com autenticação
 */
export const apiRequest = async <T = any>(
  endpoint: string,
  options: RequestInit & { token?: string } = {}
): Promise<T> => {
  const { token, ...fetchOptions } = options;
  const url = `${getApiUrl()}${endpoint}`;

  const headers: HeadersInit = {
    'Content-Type': 'application/json',
  };

  if (fetchOptions.headers) {
    Object.assign(headers, fetchOptions.headers);
  }

  if (token) {
    Object.assign(headers, { Authorization: `Bearer ${token}` });
  }

  const response = await fetch(url, {
    ...fetchOptions,
    headers,
  });

  if (!response.ok) {
    const error = await response.json().catch(() => ({ message: 'Erro desconhecido' }));
    throw new Error(error.message || `Erro ${response.status}`);
  }

  return response.json();
};

/**
 * Interface para resposta paginada
 */
export interface PaginatedResponse<T> {
  items: T[];
  total: number;
  page: number;
  per_page: number;
}

/**
 * Interface para produto monitorado
 */
export interface MonitoredProduct {
  id: string;
  name_identification: string;
  product_url: string;
  current_price: number;
  target_price: number;
  status: 'alert' | 'ok';
  last_update: string;
  competitors_count: number;
}

/**
 * Interface para concorrente
 */
export interface Competitor {
  id: string;
  monitored_product_id: string;
  product_url: string;
  name: string;
  current_price: number;
  last_update: string;
}

/**
 * Interface para alerta
 */
export interface Alert {
  id: string;
  monitored_product_id: string;
  type: string;
  message: string;
  created_at: string;
  is_read: boolean;
}

/**
 * Interface para comparação de preços
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
 * API: Listar produtos monitorados
 */
export const getMonitoredProducts = (token: string) =>
  apiRequest<MonitoredProduct[]>('/monitored', { token });

/**
 * API: Criar novo produto monitorado
 */
export const createMonitoredProduct = (
  token: string,
  data: {
    name_identification: string;
    product_url: string;
    target_price: number;
  }
) =>
  apiRequest<MonitoredProduct>('/monitored', {
    token,
    method: 'POST',
    body: JSON.stringify(data),
  });

/**
 * API: Agendar scraping de produto monitorado
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
 * API: Listar concorrentes de um produto
 */
export const getCompetitors = (token: string, monitoredProductId: string) =>
  apiRequest<Competitor[]>(`/competitors/${monitoredProductId}`, { token });

/**
 * API: Adicionar concorrente
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
 * API: Agendar scraping de concorrente
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
 * API: Listar alertas
 */
export const getAlerts = (token: string) =>
  apiRequest<Alert[]>('/alerts', { token });

/**
 * API: Marcar alerta como lido
 */
export const markAlertAsRead = (token: string, alertId: string) =>
  apiRequest<Alert>(`/alerts/${alertId}/read`, {
    token,
    method: 'POST',
  });

/**
 * API: Deletar alerta
 */
export const deleteAlert = (token: string, alertId: string) =>
  apiRequest<{ message: string }>(`/alerts/${alertId}`, {
    token,
    method: 'DELETE',
  });

/**
 * API: Rodar comparação de preços
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
 * API: Obter estatísticas do dashboard
 */
export const getDashboardStats = (token: string) =>
  apiRequest<{
    total_monitored: number;
    active_alerts: number;
    ok_prices: number;
    potential_savings: number;
  }>('/dashboard/stats', { token });
