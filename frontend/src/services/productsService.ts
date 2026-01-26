import apiClient from '../lib/api';
import {
  MonitoredProduct,
  CompetitorsListResponse,
  PriceComparisonSummary,
  PaginatedResponse,
  MonitoredProductCreateScraping,
  CompetitorProductCreateScraping,
  ScrapeCreationResponse,
  MonitoredScrapeCreationResponse,
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
  // Usa last_checked quando disponível, mantendo fallback para last_scraped_at
  const normalizedLastChecked = 
    product.last_checked ?? product.last_scraped_at ?? undefined;

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

  const normalizedPaused = product.paused ?? product.is_paused ?? false;

  return {
    ...product,
    current_price: product.current_price ?? null,
    last_checked: normalizedLastChecked,
    availability: inferredAvailability,
    is_paused: normalizedPaused,
    paused: normalizedPaused,
    paused_at: product.paused_at ?? null,
    next_check_at: product.next_check_at ?? null,
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
  ): Promise<MonitoredScrapeCreationResponse> {
    const response = await apiClient.post<MonitoredScrapeCreationResponse>(
      '/monitored/scrape',
      data
    );
    return response.data;
  },

  /**
   * Pausa um produto monitorado e retorna o estado atualizado.
   */
  async pauseMonitored(productId: string): Promise<MonitoredProduct> {
    const response = await apiClient.put<MonitoredProduct>(`/monitored/${productId}/paused`, null, {
        params: { paused: true },
      });
    return normalizeMonitoredProduct(response.data);
  },

  /**
   * Retoma o monitoramento de um produto e retorna o estado atualizado.
   */
  async resumeMonitored(productId: string): Promise<MonitoredProduct> {
    const response = await apiClient.put<MonitoredProduct>(`/monitored/${productId}/paused`, null, {
        params: { paused: false },
      });
    return normalizeMonitoredProduct(response.data);
  },

  /**
   * Remove um produto monitorado
   */
  async deleteMonitoredProduct(
    productId: string
  ): Promise<void> {
    await productsService.deleteProduct(productId);
  },

  /**
   * Remove um produto monitorado utilizando a rota padrão de deleção.
   * Mantém compatibilidade com nomenclatura mais genérica usada em handlers da UI.
   */
  async deleteProduct(productId: string): Promise<void> {
    await apiClient.delete(`/monitored/${productId}`);
  },

  /**
   * Lista concorrentes de um produto monitorado
   * - monitored_id: ID do produto monitorado (obrigatório)
   * - page, per_page: paginação
   * - order_by: campo de ordenação
   * - include_paused/include_inactive: incluir concorrentes pausados ou indisponíveis
   */
  async getCompetitors(params: {
    monitored_id: string;
    page?: number;
    per_page?: number;
    order_by?: string;
    include_paused?: boolean;
    include_inactive?: boolean;
  }): Promise<CompetitorsListResponse> {
    const requestParams = {
      include_inactive: params.include_inactive ?? true,
      include_paused: params.include_paused ?? true,
      ...params,
    };

    const response = await apiClient.get<CompetitorsListResponse>(
      '/competitors',
      { params: requestParams }
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
      competitors_total:
        response.data.competitors_total ?? normalizedItems.length,
      competitors_with_price_count:
        response.data.competitors_with_price_count ??
        normalizedItems.filter(
          (item) => item.current_price !== null && item.availability !== false
        ).length,
      excluded_due_to_inactive_count:
        response.data.excluded_due_to_inactive_count ??
        normalizedItems.filter(
          (item) => item.current_price === null || item.availability === false
        ).length,
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
   * Remove um concorrente específico
   */
  async deleteCompetitor(competitorId: string): Promise<void> {
    await apiClient.delete(`/competitors/${competitorId}`);
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
