# Contratos de produtos e comparações (market_alert)

Este documento consolida o estado atual e o contrato alvo dos endpoints de produtos monitorados, concorrentes e comparações. Ele serve como referência para frontend, workers e times de scraping durante a estabilização dos contratos e migração para respostas paginadas e idempotentes.

## Inventário do estado atual
- **GET `/monitored`**: retorna `items`, `total`, `page`, `per_page` no nível raiz, sem envelope `meta`. Os itens seguem `MonitoredProductResponse` com `product_url`, `collected_at`, `availability`, `last_status` e `is_featured`, mas não incluem `owner_id`, `thumbnail` ou `last_scraped_at`. Produtos sem preço são filtrados no serviço. [Fonte: schemas em `market_alert/schemas/schemas_products.py`, linhas 26-37; rota em `market_alert/routes/routes_monitored.py`, linhas 109-181.]
- **POST `/monitored/scrape`**: valida duplicidade por usuário + URL e agenda scraping via Celery. A resposta é apenas `{ "message": ... }` com status 202, sem retornar `id` ou timestamps. [Fonte: `market_alert/routes/routes_monitored.py`, linhas 38-107.]
- **GET `/monitored/{id}` e `/monitored/featured`**: usam o mesmo contrato simplificado de monitorados; a rota de destaques limita a 3 itens e ignora registros sem preço. [Fonte: `market_alert/routes/routes_monitored.py`, linhas 183-208.]
- **GET `/comparisons/{monitored_id}`**: utiliza parâmetros `page` (base 1) e `per_page` (1-100) e responde com envelope `{ items, meta }`. [Fonte: `market_alert/routes/routes_comparisons.py`, linhas 29-80.]
- **GET `/comparisons/{monitored_id}/summary`**: usa `PriceComparisonSummaryResponse` com `json_encoders` que convertem `Decimal` em `float`, produzindo números no JSON. [Fonte: `market_alert/routes/routes_comparisons.py`, linhas 82-105; `market_alert/schemas/schemas_comparisons.py`, linhas 27-80.]
- **GET `/competitors?monitored_id=`**: responde com `items`, `total`, `page`, `per_page` no nível raiz. O `total` corresponde aos concorrentes exibidos (sem preço são ignorados). [Fonte: `market_alert/routes/routes_competitors.py`, linhas 208-289; `market_alert/schemas/schemas_products.py`, linhas 39-53.]
- **POST `/competitors/scrape`**: valida duplicidade por `monitored_product_id` + URL, aplica rate limit opcional e retorna apenas `{ "message": ... }` com status 202. [Fonte: `market_alert/routes/routes_competitors.py`, linhas 125-206.]

## Contrato alvo consolidado

### Serialização de valores Decimais
- A API FastAPI/Pydantic serializa `Decimal` como **string** no JSON para todos os contratos, exceto onde houver encoder customizado. `PriceComparisonSummaryResponse` aplica `json_encoders={Decimal: float}` e, portanto, envia números JSON em vez de strings para os campos monetários do resumo.
- Frontend deve tratar strings numéricas como valores monetários (ex.: `"1099.90"`) e apenas no resumo esperar números literais (ex.: `1099.9`). Caso seja necessário padronizar para string em todos os pontos, um encoder global deverá substituir o encoder atual do resumo.

### Estrutura de paginação
Todas as rotas paginadas devem seguir o envelope:
```json
{
  "items": [ ... ],
  "meta": {
    "total": 123,
    "page": 1,
    "per_page": 20
  }
}
```
A página é base 1; `per_page` deve respeitar os limites já praticados por rota.

### Schemas finais
- **MonitoredProductResponse**
  - `id` (UUID), `owner_id` (UUID), `name` (string), `url` (HttpUrl), `current_price` (Decimal), `currency` (string opcional), `thumbnail` (string opcional), `is_featured` (bool), `last_scraped_at` (datetime), `availability` (bool opcional), `competitiveness_status` (enum opcional), `last_status` (string opcional).
- **CompetitorProductResponse**
  - `id` (UUID), `monitored_id` (UUID), `name` (string), `url` (HttpUrl), `current_price` (Decimal), `currency` (string opcional), `thumbnail` (string opcional), `availability` (bool opcional), `is_paused` (bool), `last_status` (string opcional), `last_scraped_at` (datetime opcional).
- **PriceComparisonResponse**
  - `id` (UUID), `monitored_id` (UUID), `timestamp` (datetime), `data` (objeto livre conforme motor de comparação).
- **PriceComparisonSummaryResponse**
  - `monitored_id` (UUID), `comparison_id` (UUID opcional), `last_comparison_at` (datetime opcional), `computed_at` (datetime opcional), `monitored_price` (Decimal), `competitors_count` (int), `competitors_with_price_count` (int), `competitors_mean|min|max` (Decimal opcional), `position_rank` (int opcional), `potential_adjustment` (Decimal opcional), `comparison_insights` (string opcional), `competitiveness_status` (enum opcional), `discrepancies` e `alerts` (listas).

### Exemplos de contrato
- **GET `/monitored?page=1&per_page=20`**
```json
{
  "items": [
    {
      "id": "7c3815bb-8c1c-4a2f-885d-0d4b6e5b113b",
      "owner_id": "3e358d88-3f2b-4c7a-9c8c-897b32f1bd38",
      "name": "Monitor Gamer 27''",
      "url": "https://loja.com/produto/123",
      "current_price": "1899.90",
      "currency": "BRL",
      "thumbnail": "https://cdn.loja.com/123.jpg",
      "is_featured": false,
      "last_scraped_at": "2024-05-30T12:45:10Z",
      "availability": true,
      "competitiveness_status": "competitivo"
    }
  ],
  "meta": { "total": 1, "page": 1, "per_page": 20 }
}
```
- **POST `/monitored/scrape`** (payload mínimo)
```json
{ "url": "https://loja.com/produto/123", "name": "Monitor Gamer 27''" }
```
Resposta esperada:
```json
{
  "id": "7c3815bb-8c1c-4a2f-885d-0d4b6e5b113b",
  "url": "https://loja.com/produto/123",
  "created_at": "2024-05-30T12:45:10Z"
}
```
- **GET `/comparisons/{monitored_id}/summary`**
```json
{
  "monitored_id": "7c3815bb-8c1c-4a2f-885d-0d4b6e5b113b",
  "comparison_id": "6f2c43c0-0ea2-4d5d-b39a-2c42b55e9de5",
  "last_comparison_at": "2024-05-30T12:45:10Z",
  "computed_at": "2024-05-30T12:45:10Z",
  "monitored_price": 1899.9,
  "competitors_count": 4,
  "competitors_with_price_count": 3,
  "competitors_mean": 1949.9,
  "competitors_min": 1849.0,
  "competitors_max": 2149.9,
  "position_rank": 2,
  "potential_adjustment": -50.9,
  "comparison_insights": "Preço está 2,7% acima da média.",
  "competitiveness_status": "atencao",
  "discrepancies": [],
  "alerts": []
}
```

### Pontos de migração
- Ajustar envelopes de paginação para incluir `meta` e alinhar `total` ao número real de registros, não apenas aos itens exibidos.
- Incluir `owner_id`, `thumbnail` e `last_scraped_at` nos contratos de monitorados e concorrentes, mantendo compatibilidade com o frontend atual.
- Atualizar respostas 202 dos endpoints de scraping para retornarem a representação mínima do recurso criado (`id`, `url`, `created_at`).
- Definir encoder global para `Decimal` caso seja necessária consistência absoluta entre resumo e demais respostas.
- Comparações são recalculadas automaticamente pelas tasks de monitoramento/compare (`tasks.compare_prices_tasks.compare_prices_task`), sem endpoint para disparo manual.
