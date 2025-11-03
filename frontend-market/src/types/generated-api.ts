/*
  "" Tipagens enxutas inspiradas no contrato OpenAPI; substitua por geração automática quando disponível """
*/

export type AuthToken = {
  access_token: string
  token_type: 'bearer'
}

export type MonitoredProduct = {
  id: string
  user_id: string
  name_identification: string | null
  monitoring_type: 'scraping' | 'search' | 'manual'
  search_query: string | null
  product_url: string | null
  target_price: string | number
  current_price: string | number | null
  free_shipping?: boolean | null
  thumbnail?: string | null
  status?: 'active' | 'pending' | 'paused' | 'error'
  last_checked?: string | null
}

export type CreateMonitoredDto = {
  name_identification: string
  product_url: string
  target_price?: number | null
}

export type CompetitorProduct = {
  id: string
  monitored_product_id: string
  name_competitor: string
  product_url: string
  current_price: string | number
  old_price?: string | number | null
  free_shipping?: boolean | null
  seller?: string | null
  seller_rating?: number | null
  thumbnail?: string | null
  status?: string | null
  last_checked?: string | null
  created_at?: string | null
  updated_at?: string | null
}

export type PriceComparison = {
  id: string
  monitored_product_id: string
  timestamp: string
  data: Record<string, unknown>
}

export type ManualComparisonPayload = {
  tolerance?: number
  price_change_threshold?: number
}

export type ManualComparisonResult = Record<string, unknown>
