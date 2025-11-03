/*
  Este arquivo é um placeholder com tipos mínimos para desenvolvimento inicial.
  Recomendação: execute o script `npm run generate-types` apontando para a URL do backend
  (por exemplo: http://localhost:8000/openapi.json) para gerar tipos completos.
*/

export type AuthToken = {
  access_token: string
  token_type: 'bearer'
}

export type MonitoredProduct = {
  id: string
  name_identification: string
  product_url: string
  current_price?: number | null
}

export type CreateMonitoredDto = {
  name_identification: string
  product_url: string
  target_price?: number | null
}

export type ComparisonResult = {
  monitored_id: string
  compared_at: string
  summary?: any
}
