/**
 * Cliente HTTP para comunicação com o backend market_alert
 *
 * Contém funções utilitárias para chamadas HTTP autenticadas e
 * tipos/contratos usados pelo frontend para consumir a API.
 */

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
export interface MonitoredProduct {
  id: string;
  name_identification: string;
  product_url: string;
  current_price: number;
  target_price: number;
  status: 'alert' | 'ok'; // 'alert' quando está abaixo do target/critério
  last_update: string; // ISO timestamp da última coleta
  competitors_count: number; // número de concorrentes cadastrados
}

/**
 * Interface para concorrente (Competitor).
 * Representa um produto similar cadastrado como concorrente de um monitorado.
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
 * Interface para alerta (Alert).
 * Útil para notificar mudanças de preço/regras disparadas.
 */
export interface Alert {
  id: string;
  monitored_product_id: string;
  type: string; // tipo/slug do alerta
  message: string; // mensagem descritiva do alerta
  created_at: string;
  is_read: boolean;
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
export const getMonitoredProducts = (token: string) =>
  apiRequest<MonitoredProduct[]>('/monitored', { token });

/**
 * API: Criar novo produto monitorado.
 * POST /monitored
 * Body esperado: { name_identification, product_url, target_price }
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
 * API: Listar alertas do usuário.
 * GET /alerts
 */
export const getAlerts = (token: string) =>
  apiRequest<Alert[]>('/alerts', { token });

/**
 * API: Marcar alerta como lido.
 * POST /alerts/{alertId}/read
 */
export const markAlertAsRead = (token: string, alertId: string) =>
  apiRequest<Alert>(`/alerts/${alertId}/read`, {
    token,
    method: 'POST',
  });

/**
 * API: Deletar alerta.
 * DELETE /alerts/{alertId}
 */
export const deleteAlert = (token: string, alertId: string) =>
  apiRequest<{ message: string }>(`/alerts/${alertId}`, {
    token,
    method: 'DELETE',
  });

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
