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
  BulkActionResponse,
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
   * Lista produtos monitorados com paginação e filtros
   * - page: número da página (padrão no backend)
   * - per_page: itens por página
   * - query: texto de busca
   * - status: filtro por status do monitoramento
   *
   * @param {Object} params Parâmetros de paginação e filtro
   * @returns {Promise<PaginatedResponse<MonitoredProduct>>} Resposta paginada de produtos monitorados
   */
  async getMonitoredProducts(params?: {
    page?: number;
    per_page?: number;
    query?: string;
    status?: string;
  }): Promise<PaginatedResponse<MonitoredProduct>> {
    const response = await apiClient.get<PaginatedResponse<MonitoredProduct>>(
      '/monitored',
      { params }
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
    return response.data;
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
   * Remove concorrentes de um produto monitorado
   * Remove todos os concorrentes associados ao ID do produto monitorado.
   */
  async deleteCompetitors(
    monitoredProductId: string
  ): Promise<CompetitorProduct[]> {
    const response = await apiClient.delete<CompetitorProduct[]>(
      `/competitors/${monitoredProductId}`
    );
    return response.data;
  },

  /**
   * Pausa concorrentes em massa
   * Envia uma requisição para pausar múltiplos concorrentes.
   */
  async pauseCompetitors(
    competitorIds: string[]
  ): Promise<BulkActionResponse> {
    const response = await apiClient.post('/competitors/bulk/pause', {
      competitor_ids: competitorIds,
    });
    return response.data;
  },

  /**
   * Retoma concorrentes em massa
   * Reverte a ação de pausa para os concorrentes informados.
   */
  async resumeCompetitors(
    competitorIds: string[]
  ): Promise<BulkActionResponse> {
    const response = await apiClient.post('/competitors/bulk/resume', {
      competitor_ids: competitorIds,
    });
    return response.data;
  },

  /**
   * Remove concorrentes em massa
   * Aciona o endpoint que exclui vários concorrentes de uma só vez.
   */
  async removeCompetitors(
    competitorIds: string[]
  ): Promise<BulkActionResponse> {
    const response = await apiClient.post('/competitors/bulk/remove', {
      competitor_ids: competitorIds,
    });
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
    return response.data;
  },
};
