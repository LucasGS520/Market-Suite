/**
 * Representa um usuário do sistema.
 */
export interface User {
  id: string; // Identificador único do usuário (UUID)
  email: string; // Email utilizado para autenticação/contato
  name?: string; // Nome completo ou apelido (opcional)
  is_active: boolean; // Indica se a conta está ativa
  is_verified: boolean; // Indica se o email/conta já foi verificado
  created_at: string; // Timestamp de criação do usuário (ISO 8601)
}

/**
 * Par de tokens retornado pela autenticação.
 */
export interface TokenPair {
  access_token: string; // Token de acesso (usado nos headers Authorization)
  refresh_token: string; // Token para refresh de sessão
  token_type: string; // Tipo do token, ex: "bearer"
}

/**
 * Produto monitorado pelo usuário no Market-Suite.
 */
export interface MonitoredProduct {
  id: string; // Identificador do produto monitorado
  owner_id: string; // ID do usuário que monitora o produto
  name: string; // Nome do produto
  url: string; // URL do produto
  current_price: string; // Preço atual do produto
  currency?: string; // Código da moeda
  thumbnail?: string; // URL da imagem em miniatura
  is_featured: boolean; // Indica se o produto é destacado
  last_scraped_at?: string; // Timestamp do último scraping
  availability?: boolean; // Disponibilidade do produto
  competitiveness_status?: CompetitivenessStatus; // Status de competitividade
  last_status?: string; // Último status registrado
}

/**
 * Produto concorrente relacionado a um produto monitorado.
 */
export interface CompetitorProduct {
  id: string; // Identificador do produto concorrente
  monitored_id: string; // ID do produto monitorado ao qual este pertence
  name: string; // Nome do produto concorrente
  url: string; // URL do produto concorrente
  current_price: string; // Preço atual do concorrente (string para preservar formato)
  currency?: string; // Código da moeda (opcional)
  thumbnail?: string; // URL da imagem em miniatura (opcional)
  availability?: boolean; // Disponibilidade do concorrente (opcional)
  is_paused: boolean; // Indica se a monitoria desse concorrente está pausada
  last_status?: string; // Último status textual registrado (opcional)
  last_scraped_at?: string; // Timestamp do último scraping desse concorrente (opcional)
}

/**
 * Registro de comparação de preços gerado por um scraping/processamento.
 */
export interface PriceComparison {
  id: string; // Identificador único da comparação
  monitored_id: string; // ID do produto monitorado
  timestamp: string; // Timestamp da comparação
  data: Record<string, any>; // Payload genérico com dados da comparação
}

/**
 * Resumo agregado de uma comparação de preços, usado em dashboards/visões rápidas.
 */
export interface PriceComparisonSummary {
  monitored_id: string; // ID do produto monitorado
  comparison_id?: string; // ID da comparação associada
  last_comparison_at?: string; // Última vez que houve uma comparação
  computed_at?: string; // Quando esse resumo foi computado
  monitored_price: number; // Preço do produto monitorado
  competitors_count: number; // Quantidade total de concorrentes considerados
  competitors_with_price_count: number; // Quantidade de concorrentes com preço disponível
  competitors_mean?: number; // Média dos preços dos concorrentes
  competitors_min?: number; // Menor preço entre concorrentes
  competitors_max?: number; // Maior preço entre concorrentes
  position_rank?: number; // Posição/ranking do monitorado
  potential_adjustment?: number; // Ajuste de preço sugerido
  comparison_insights?: string; // Insights textuais adicionais
  competitiveness_status?: CompetitivenessStatus; // Status de competitividade
  discrepancies: any[]; // Lista de discrepâncias detectadas
  alerts: any[]; // Alertas gerados a partir dessa comparação
}

/**
 * Regra de alerta associada a um produto monitorado.
 */
export interface AlertRule {
  id: string; // Identificador da regra
  monitored_product_id: string; // Produto monitorado ao qual a regra pertence
  rule_type: string; // Tipo de regra (ex: "preco_maior_que", "queda_percentual")
  threshold_value?: string; // Valor limite usado pela regra (opcional, formato string para flexibilidade)
  is_active: boolean; // Indica se a regra está ativa
  created_at: string; // Timestamp de criação (ISO 8601)
  updated_at: string; // Timestamp da última atualização (ISO 8601)
}

/**
 * Log de notificações disparadas pelo sistema.
 */
export interface NotificationLog {
  id: string; // Identificador do log
  alert_rule_id: string; // Regra de alerta que originou a notificação
  channel: string; // Canal usado para envio (ex: "email", "slack")
  message: string; // Mensagem enviada
  sent_at: string; // Timestamp do envio (ISO 8601)
  success: boolean; // Indica se o envio foi bem sucedido
  error_message?: string; // Mensagem de erro caso o envio tenha falhado (opcional)
}

/**
 * Estatísticas agregadas exibidas no dashboard principal.
 */
export interface DashboardStats {
  total_monitored: number; // Total de produtos monitorados
  active_alerts: number; // Quantidade de alertas ativos
  ok_prices: number; // Quantidade de preços considerados como "ok"
  total_competitors: number; // Total de produtos concorrentes cadastrados
}

/**
 * Formato genérico de resposta paginada da API.
 */
export interface PaginatedResponse<T> {
  items: T[]; // Itens retornados na página
  
  /** Metadados de paginação */
  meta: {
    total: number; // Total de itens disponíveis
    page: number; // Página atual (1-based)
    per_page: number; // Itens por página
  };
}

/**
 * Tipos possíveis para o status de competitividade.
 * - competitivo: posição confortável/competitiva
 * - atencao: requer atenção
 * - nao_competitivo: não competitivo
 * - urgente: ação urgente recomendada
 */
export type CompetitivenessStatus = 'competitivo' | 'atencao' | 'nao_competitivo' | 'urgente';

/**
 * Payload usado para criar um scraping ao cadastrar um produto monitorado.
 */
export interface MonitoredProductCreateScraping {
  url: string; // URL do produto a ser raspado
  name?: string; // Nome opcional para melhor identificação
}

/**
 * Payload usado para criar um scraping para um concorrente.
 */
export interface CompetitorProductCreateScraping {
  monitored_product_id: string; // ID do produto monitorado pai
  url: string; // URL do concorrente a ser raspado
  name?: string; // Nome opcional do concorrente
}

/**
 * Resposta mínima retornada ao criar um job de scraping.
 */
export interface ScrapeCreationResponse {
  id: string; // ID do job criado
  url: string; // URL alvo do scraping
  created_at: string; // Timestamp de criação
}
