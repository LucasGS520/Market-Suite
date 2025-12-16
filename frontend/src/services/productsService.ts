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
} from '../types';

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
    return response.data;
  },

  /**
   * Obtém produtos em destaque para o dashboard
   * Retorna uma lista curta de produtos para exibição em áreas de destaque.
   */
  async getFeaturedProducts(): Promise<MonitoredProduct[]> {
    const response = await apiClient.get<MonitoredProduct[]>('/monitored/featured');
    return response.data;
  },

  /**
   * Obtém detalhes de um produto monitorado
   */
  async getMonitoredProduct(
    productId: string
  ): Promise<MonitoredProduct> {
    const response = await apiClient.get<MonitoredProduct>(`/monitored/${productId}`);
    return response.data;
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
