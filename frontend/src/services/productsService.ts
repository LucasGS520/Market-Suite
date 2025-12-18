import apiClient from '../lib/api';
import {
  MonitoredProduct,
  CompetitorProduct,
  PriceComparisonSummary,
  PaginatedResponse,
  MonitoredProductCreateScraping,
  CompetitorProductCreateScraping,
  ScrapeCreationResponse,
  DashboardStats,
  CompetitivenessStatus,
} from '../types';

/**
 * Identifica sinais de indisponibilidade vindos do backend via last_status.
 * Inclui termos comuns retornados pelo scraper para evitar falsos positivos de disponibilidade.
 */
const isUnavailableFromLastStatus = (lastStatus?: string): boolean => {
  if (!lastStatus) return false;

  const normalized = lastStatus
    .toLowerCase()
    .normalize('NFD')
    .replace(/[\u0300-\u036f]/g, '')
    .replace(/[^a-z0-9]+/g, ' ')
    .trim();

  const unavailableSignals = [
    'indisponivel',
    'indisponivel no momento',
    'sem estoque',
    'sem estoque no momento',
    'sold out',
    'soldout',
    'sold_out',
    'no stock',
    'removed',
    'unavailable',
    'not available',
    'paused by seller',
  ];

  return unavailableSignals.some((signal) => normalized.includes(signal));
};

/**
 * Sanitiza o status de competitividade para que apenas valores com concorrentes relevantes sejam propagados.
 * Evita badges enganosos quando não há comparativos de preço disponíveis.
 */
const sanitizeCompetitivenessStatus = (
  status: CompetitivenessStatus | undefined,
  summary?: PriceComparisonSummary
): CompetitivenessStatus | undefined => {
  const competitorsWithPrice = summary?.competitors_with_price_count ?? 0;
  const competitorsCount = summary?.competitors_count ?? 0;

  if (!status) return undefined;
  if (competitorsWithPrice <= 0 && competitorsCount <= 0) return undefined;
  if (competitorsWithPrice <= 0) return undefined;

  return status;
};

/**
 * Normaliza campos centrais de produtos monitorados para evitar nullables inconsistentes.
 * Garante que disponibilidade, pausa e resumo de comparação estejam preenchidos e coerentes.
 */
const normalizeMonitoredProduct = (product: MonitoredProduct): MonitoredProduct => {
  const comparisonSummary =
    product.comparison_summary === undefined ? undefined : product.comparison_summary;

  const inferredAvailability =
    product.availability === false || isUnavailableFromLastStatus(product.last_status)
      ? false
      : product.availability ?? undefined;

  const normalizedSummary = comparisonSummary
    ? {
        ...comparisonSummary,
        competitors_count: comparisonSummary.competitors_count ?? 0,
        competitors_with_price_count: comparisonSummary.competitors_with_price_count ?? 0,
        ignored_due_to_inactive: Boolean(comparisonSummary.ignored_due_to_inactive),
      }
    : comparisonSummary;

  const competitivenessStatus = sanitizeCompetitivenessStatus(
    product.competitiveness_status || normalizedSummary?.competitiveness_status || undefined,
    normalizedSummary
  );

  let displayStatus = product.display_status;
  const hasCompetitors = (normalizedSummary?.competitors_with_price_count ?? 0) > 0;

  if (inferredAvailability === false || normalizedSummary?.ignored_due_to_inactive) {
    displayStatus = 'inactive';
  }

  if (
    displayStatus &&
    ['competitive', 'attention', 'urgent'].includes(displayStatus) &&
    (!hasCompetitors || inferredAvailability === false)
  ) {
    displayStatus = hasCompetitors ? displayStatus : 'no_competitors';
    if (inferredAvailability === false) displayStatus = 'inactive';
  }

  return {
    ...product,
    current_price: product.current_price ?? null,
    availability: inferredAvailability,
    is_paused: product.is_paused ?? false,
    comparison_summary: normalizedSummary,
    competitiveness_status: competitivenessStatus,
    display_status: displayStatus,
  };
};

/**
 * Serviço de produtos
 *
 * Responsável por encapsular as chamadas HTTP para endpoints relacionados a:
 * - Estatísticas do dashboard
 * - Produtos monitorados (CRUD básico + criação via scraping)
 * - Concorrentes (listagem, criação via scraping, ações em massa)
 * - Resumo de comparação de preços
 *
 * As funções retornam o campo `data` da resposta Axios para simplificar o uso nos componentes.
 */
export const productsService = {
  /**
   * Obtém estatísticas do dashboard
   * Retorna métricas e contadores usados na visão geral do sistema.
   */
  async getDashboardStats(): Promise<DashboardStats> {
    const response = await apiClient.get<DashboardStats>('/dashboard/stats');
    return response.data;
  },

  /**
   * Lista produtos monitorados com filtros opcionais e paginação sob demanda.
   *
   * A função apenas envia parâmetros definidos, permitindo que o frontend
   * assuma paginação client-side quando necessário sem forçar `per_page` ou
   * `page` por padrão.
   */
  async getMonitoredProducts(params?: {
    page?: number;
    per_page?: number;
    query?: string;
    status?: string;
  }): Promise<PaginatedResponse<MonitoredProduct>> {
    const sanitizedParams = params
      ? Object.fromEntries(
          Object.entries(params).filter(([, value]) => value !== undefined && value !== null)
        )
      : undefined;

    const response = await apiClient.get<PaginatedResponse<MonitoredProduct>>(
      '/monitored',
      { params: sanitizedParams }
    );
    const normalizedItems = (response.data.items || []).map(normalizeMonitoredProduct);

    return {
      ...response.data,
      items: normalizedItems,
    };
  },

  /**
   * Obtém produtos em destaque para o dashboard
   * Retorna uma lista curta de produtos para exibição em áreas de destaque.
   */
  async getFeaturedProducts(): Promise<MonitoredProduct[]> {
    const response = await apiClient.get<MonitoredProduct[]>('/monitored/featured');
    return (response.data || []).map(normalizeMonitoredProduct);
  },

  /**
   * Obtém detalhes de um produto monitorado
   */
  async getMonitoredProduct(
    productId: string
  ): Promise<MonitoredProduct> {
    const response = await apiClient.get<MonitoredProduct>(`/monitored/${productId}`);
    return normalizeMonitoredProduct(response.data);
  },

  /**
   * Cria um novo produto monitorado via scraping
   * O endpoint realiza scraping do URL informado e inicia o fluxo de persistência/monitoramento.
   */
  async createMonitoredProduct(
    data: MonitoredProductCreateScraping
  ): Promise<ScrapeCreationResponse> {
    const response = await apiClient.post<ScrapeCreationResponse>(
      '/monitored/scrape',
      data
    );
    return response.data;
  },

  /**
   * Remove um produto monitorado
   */
  async deleteMonitoredProduct(
    productId: string
  ): Promise<MonitoredProduct> {
    const response = await apiClient.delete<MonitoredProduct>(`/monitored/${productId}`);
    return response.data;
  },

  /**
   * Lista concorrentes de um produto monitorado
   * - monitored_id: ID do produto monitorado (obrigatório)
   * - page, per_page: paginação
   * - order_by: campo de ordenação
   * - include_paused: incluir concorrentes pausados
   */
  async getCompetitors(params: {
    monitored_id: string;
    page?: number;
    per_page?: number;
    order_by?: string;
    include_paused?: boolean;
  }): Promise<PaginatedResponse<CompetitorProduct>> {
    const response = await apiClient.get<PaginatedResponse<CompetitorProduct>>(
      '/competitors',
      { params }
    );
    const normalizedItems = (response.data.items || []).map((competitor) => {
      const fallbackName = (() => {
        try {
          return new URL(competitor.url).hostname;
        } catch {
          return 'Concorrente';
        }
      })();

      const displayName = competitor.display_name || competitor.name || competitor.title || fallbackName;

      return {
        ...competitor,
        display_name: competitor.display_name || competitor.name || competitor.title,
        name: displayName,
        current_price: competitor.current_price ?? null,
        monitored_id: competitor.monitored_id || competitor.monitored_product_id || params.monitored_id,
        monitored_product_id: competitor.monitored_product_id || competitor.monitored_id || params.monitored_id,
      };
    });

    return {
      ...response.data,
      items: normalizedItems,
    };
  },

  /**
   * Cria um novo concorrente via scraping
   * Similar à criação de produto monitorado, aciona o scraper para o concorrente informado.
   */
  async createCompetitor(
    data: CompetitorProductCreateScraping
  ): Promise<ScrapeCreationResponse> {
    const response = await apiClient.post<ScrapeCreationResponse>(
      '/competitors/scrape',
      data
    );
    return response.data;
  },

  /**
   * Obtém resumo de comparação de preços
   * Retorna um resumo das comparações de preços para um produto monitorado específico,
   * usado em relatórios e widgets de comparação.
   */
  async getPriceComparisonSummary(
    monitoredId: string
  ): Promise<PriceComparisonSummary> {
    const response = await apiClient.get<PriceComparisonSummary>(
      `/comparisons/${monitoredId}/summary`
    );
    const summary = response.data || {};

    return {
      ...summary,
      monitored_id: summary.monitored_id || summary.monitored_product_id || monitoredId,
      monitored_product_id: summary.monitored_product_id || summary.monitored_id || monitoredId,
      competitors_count: summary.competitors_count ?? 0,
      competitors_with_price_count: summary.competitors_with_price_count ?? 0,
      competitors_mean: summary.competitors_mean ?? null,
      competitors_min: summary.competitors_min ?? null,
      competitors_max: summary.competitors_max ?? null,
      monitored_price: summary.monitored_price ?? null,
      potential_adjustment: summary.potential_adjustment ?? null,
      position_rank: summary.position_rank ?? null,
      discrepancies: summary.discrepancies || [],
      alerts: summary.alerts || [],
    };
  },
};
