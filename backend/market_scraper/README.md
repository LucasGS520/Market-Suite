# Market Scraper

Serviço FastAPI responsável por transformar uma URL de produto em `ParserResponse`, executando um pipeline determinístico de coleta, extração e pós-processamento. Preserva o contrato HTTP compartilhado com `market_alert` e não mantém estado — cada requisição é autônoma.

## Relações e Referências

- Visão arquitetural da suite: [`../README.md`](../README.md)
- Consumidor principal: [`../market_alert/README.md`](../market_alert/README.md)
- Orquestrador durável: [`../market_orchestrator/README.md`](../market_orchestrator/README.md)
- Contratos compartilhados: [`../shared/README.md`](../shared/README.md)

---

## Principais Responsabilidades

- **Coletar HTML** de URLs de produto via HTTP (`curl_cffi`) com fallback para browser (`Playwright`) quando detectado anti-bot ou resposta inválida.
- **Extrair dados estruturados** com cadeia determinística em ordem fixa: `extruct → parsel → bs4+lxml`.
- **Normalizar e validar** preço, disponibilidade, fonte e telemetria de aquisição.
- **Responder no contrato público** `ParserResponse` com headers de cache condicional (`ETag`, `Last-Modified`, `304`).
- **Observar** cada etapa com `trace_id` obrigatório, logs estruturados e eventos de telemetria canônicos.

---

## Estrutura do Diretório

```text
market_scraper/
├── routes/                    # Transporte HTTP — casca fina de entrada e saída
├── scraper_orchestrator/      # Use case canônico e interface pública do pipeline
├── collection/                # Coleta de HTML: política, coletores e DTOs
│   ├── collectors/            #   HttpCollector (curl_cffi via Crawlee), BrowserCollector (Playwright)
│   ├── crawler/               #   CrawleeRuntime — coordena HTTP → browser com política de decisão
│   └── dto/                   #   CollectedDocument, CollectionAttempt
├── extraction/                # Extração de dados: cadeia determinística e parsers
│   ├── parsers/               #   extruct, parsel, beautifulsoup
│   └── extraction_chain.py    #   cadeia fixa; usa ParseResult/ParseAttempt de domain.dtos
├── post_processing/           # Normalização e validação pós-extração
│   ├── normalizers/           #   PriceNormalizer, ProductNormalizer
│   └── processor.py           #   PostProcessor — orquestra normalização e validação
├── services/                  # Serviços de suporte compartilhados
│   ├── availability_inference.py   # Inferência de disponibilidade por status HTTP
│   ├── response_classifier.py      # Classificação de resposta HTTP / anti-bot
│   └── telemetry_service.py        # Emissão de eventos estruturados
├── infra/                     # Infraestrutura — cache, limites, logging, robots, erros
│   ├── cache/                 #   Cache condicional, singleflight, TTL
│   ├── limits/                #   AdaptiveRateLimiter por domínio
│   ├── logging/               #   StructuredLogger com contexto obrigatório
│   ├── robots.py              #   Validação robots.txt com cache Redis
│   └── errors_map.py          #   Taxonomia canônica: erro interno → (error_code, mensagem, http_status)
├── domain/                    # DTOs de domínio compartilhados entre camadas
├── utils/                     # Utilitários: HTTP, preço, builders de resposta, robots
├── core/                      # Configuração do serviço (Settings)
├── tests/                     # Suite de testes unitários e de integração
└── main.py                    # Entry point FastAPI
```

---

## Arquitetura e Fluxo Canônico

### Diagrama de Camadas

```
┌──────────────────────────────────────────────────────────┐
│  routes/routes_scraper.py                                │
│  Normaliza URL · valida DNS · verifica cache condicional │
│  Emite trace_id · delega ao use case · mapeia resultado  │
└────────────────────┬─────────────────────────────────────┘
                     │ ParseProduct.execute()
┌────────────────────▼─────────────────────────────────────┐
│  scraper_orchestrator/parse_product.py                   │
│  robots → rate limiter → collect → extract               │
│  → post_process → build_parser_response                  │
│  Retorna: ParseProductSuccess | NoResult | Error         │
└──────┬──────────────────┬──────────────────┬─────────────┘
       │                  │                  │
┌──────▼──────┐  ┌────────▼──────┐  ┌────────▼────────────┐
│ collection/ │  │ extraction/   │  │ post_processing/    │
│             │  │               │  │                     │
│ CrawleeRun- │  │ Extraction-   │  │ PostProcessor       │
│ time        │  │ Chain         │  │ PriceNormalizer     │
│ HTTP → brow-│  │ extruct       │  │ ProductNormalizer   │
│ ser fallback│  │ → parsel      │  │ PayloadUsefulness-  │
│             │  │ → bs4+lxml    │  │ Validator           │
└──────┬──────┘  └───────────────┘  └─────────────────────┘
       │
┌──────▼──────────────────────────────┐
│ collectors/                         │
│ HttpCollector (curl_cffi/Crawlee)   │
│ PlaywrightBrowserCollector          │
└──────┬──────────────────────────────┘
       │
┌──────▼──────────────────────────────────────────────────┐
│  infra/                                                 │
│  cache/ · limits/ · logging/ · robots · errors_map     │
└─────────────────────────────────────────────────────────┘
```

### Fluxo de Execução (caminho feliz)

```
POST /scraper/parse
    │
    ├── [routes] Normaliza URL, resolve DNS público, verifica ETag/Last-Modified
    │     └── cache hit → 304 Not Modified (responde imediatamente)
    │
    ├── [orchestrator] ParseProduct.execute(url, trace_id)
    │
    ├── [stage 1] robots check
    │     └── mode=block + disallowed → 403 Forbidden
    │
    ├── [stage 2] rate limiter pre-check
    │     └── domínio em cooldown → 429 Too Many Requests
    │
    ├── [stage 3] collect — CrawleeRuntime.fetch_with_fallback()
    │     ├── HTTP via curl_cffi (budget: SCRAPER_HTTP_BUDGET_SECONDS)
    │     │     ├── ACCEPT           → HTML válido, segue para extração
    │     │     ├── ESCALATE_TO_BROWSER → aciona fallback Playwright
    │     │     ├── STOP_UNAVAILABLE → 404/410/451 → payload de indisponibilidade
    │     │     └── STOP_FAILURE     → 503/504
    │     └── browser via Playwright (budget: SCRAPER_BROWSER_BUDGET_SECONDS)
    │           └── falha → 503 pipeline_degraded
    │
    ├── [stage 4] extract — ExtractionChain.run(html)
    │     ├── extruct  → payload útil? → para cadeia
    │     ├── parsel   → payload útil? → para cadeia
    │     └── bs4+lxml → payload útil? → para cadeia
    │           └── nenhum extraiu → 422 no_result
    │
    ├── [stage 5] post_process — PostProcessor.run(payload, acquisition)
    │     ├── normaliza preço (string → Decimal)
    │     ├── infere disponibilidade
    │     ├── merge de campos de produto
    │     └── consolida telemetria de aquisição em extra_fields["acquisition"]
    │
    └── [stage 6] build_parser_response → ParserResponse → 200 OK
```

### Cenários Alternativos

| Cenário | Status | `error_code` |
|---------|--------|--------------|
| URL inválida ou host privado | `400` | `invalid_request` |
| robots.txt disallowed (`mode=block`) | `403` | `robots_disallowed` |
| Cache hit (ETag / Last-Modified) | `304` | — |
| Anti-bot ativo, bypass falhou | `429` | `anti_bot_page` |
| Rate limiter em cooldown | `429` | `rate_limiter_cooldown` |
| Extração retornou vazio | `422` | `no_result` |
| Browser pool indisponível | `503` | `pipeline_degraded` |
| Timeout global do pipeline | `504` | `playwright_timeout` |

---

## Contrato HTTP

### Endpoint Principal

```
POST /scraper/parse
Content-Type: application/json

{
  "url": "https://www.mercadolivre.com.br/produto/MLBxxx",
  "metadata": {
    "force_refresh": false
  }
}
```

**Resposta de sucesso (`200 OK`):**

```json
{
  "name": "Nome do produto",
  "current_price": 199.90,
  "currency": "BRL",
  "availability": true,
  "last_status": "available",
  "url": "https://...",
  "source": "mercadolivre.com.br",
  "payload": {
    "acquisition": {
      "layer_used": "http",
      "fallback_taken": false,
      "anti_bot_detected": false,
      "http_status": 200
    }
  }
}
```

**Resposta de erro:**

```json
{
  "detail": "Página de proteção anti-bot detectada; tente novamente mais tarde",
  "error_code": "anti_bot_page",
  "trace_id": "abc-123-..."
}
```

### Status Codes

| Status | Significado |
|--------|-------------|
| `200` | Parse concluído com payload normalizado |
| `304` | Representação não modificada (ETag / Last-Modified) |
| `400` | URL inválida, host privado ou request malformada |
| `403` | URL bloqueada por robots.txt (`mode=block`) |
| `422` | Nenhum parser extraiu dados suficientes (`no_result`) |
| `429` | Anti-bot detectado ou domínio em cooldown |
| `503` | Browser pool indisponível ou falha de coleta |
| `504` | Timeout do pipeline (HTTP ou browser) |

### Headers de Resposta

| Header | Descrição |
|--------|-----------|
| `ETag` | Hash do payload para cache condicional |
| `Last-Modified` | Timestamp da última coleta bem-sucedida |
| `Cache-Control` | Diretivas de cache para consumidores |
| `X-MarketScraper-Contract-Version` | Versão major do contrato (`v1`) |

**Headers de requisição suportados para cache condicional:**

| Header | Efeito |
|--------|--------|
| `If-None-Match` | Responde `304` se ETag não mudou |
| `If-Modified-Since` | Responde `304` se não houve atualização |

---

## Camadas e Componentes-Chave

### Routes — [`routes/routes_scraper.py`](routes/routes_scraper.py)

Casca fina de transporte. Não contém lógica de negócio. Responsabilidades:
- Normalizar e validar URL de entrada (DNS público, protocolo)
- Verificar cache condicional (`ETag` / `Last-Modified`)
- Emitir `trace_id` e delegar ao `ParseProduct`
- Mapear `ParseProductResult` tipado para resposta HTTP

### Orchestrator — [`scraper_orchestrator/parse_product.py`](scraper_orchestrator/parse_product.py)

Use case canônico. Sequência fixa sem feature flags:

```python
result: ParseProductResult = await ParseProduct().execute(url, request_logger=logger)
# ParseProductSuccess | ParseProductNoResult | ParseProductError
```

A interface pública do módulo é exposta por [`scraper_orchestrator/orchestrator.py`](scraper_orchestrator/orchestrator.py).

### Collection — [`collection/`](collection/)

| Componente | Arquivo | Papel |
|-----------|---------|-------|
| `CrawleeRuntime` | [`crawler/crawlee_runtime.py`](collection/crawler/crawlee_runtime.py) | Coordena HTTP → browser com política de decisão; lifecycle via `startup()`/`shutdown()` |
| `HttpCollector` | [`collectors/http_collector.py`](collection/collectors/http_collector.py) | Wrapper fino sobre `CurlImpersonateHttpClient` do Crawlee (curl_cffi com impersonation) |
| `PlaywrightBrowserCollector` | [`collectors/browser_collector.py`](collection/collectors/browser_collector.py) | Fallback browser via Playwright; fingerprint delegado ao Crawlee, resource blocking habilitado |
| `ResponseClassifierPolicy` | [`policy.py`](collection/policy.py) | Decide `ACCEPT / ESCALATE_TO_BROWSER / STOP_UNAVAILABLE / STOP_FAILURE` |
| `CollectedDocument` | [`dto/collected_document.py`](collection/dto/collected_document.py) | DTO imutável com HTML, status e telemetria de coleta |

### Extraction — [`extraction/`](extraction/)

Cadeia determinística em ordem fixa. Para na primeira extração válida e útil.

| Parser | Arquivo | Estratégia |
|--------|---------|------------|
| `extruct` | [`parsers/extruct.py`](extraction/parsers/extruct.py) | JSON-LD, Microdata, OpenGraph, RDFa embutidos no HTML |
| `parsel` | [`parsers/parsel.py`](extraction/parsers/parsel.py) | Seletores CSS/XPath otimizados para e-commerce |
| `bs4+lxml` | [`parsers/beautifulsoup.py`](extraction/parsers/beautifulsoup.py) | Parsing tolerante de HTML para estruturas irregulares |

### Post-Processing — [`post_processing/`](post_processing/)

| Componente | Arquivo | Papel |
|-----------|---------|-------|
| `PostProcessor` | [`processor.py`](post_processing/processor.py) | Orquestra normalização, validação e consolidação de telemetria |
| `PriceNormalizer` | [`normalizers/price_normalizer.py`](post_processing/normalizers/price_normalizer.py) | String de preço → `Decimal` |
| `ProductNormalizer` | [`normalizers/product_normalizer.py`](post_processing/normalizers/product_normalizer.py) | Merge de campos de produto com precedência definida |
| `PostProcessResult.is_useful` | [`domain/dtos.py`](domain/dtos.py) | Fonte canônica para utilidade do resultado pós-processado |

### Services — [`services/`](services/)

Serviços unitários compartilhados por múltiplas camadas do pipeline.

| Componente | Arquivo | Papel |
|-----------|---------|-------|
| `TelemetryService` | [`telemetry_service.py`](services/telemetry_service.py) | Emite eventos estruturados com `trace_id` e `domain` |
| `ResponseClassifier` | [`response_classifier.py`](services/response_classifier.py) | Classifica resposta HTTP e detecta padrões anti-bot |
| `availability_inference` | [`availability_inference.py`](services/availability_inference.py) | Infere disponibilidade de produto a partir de status HTTP |

### Infrastructure — [`infra/`](infra/)

| Componente | Arquivo | Papel |
|-----------|---------|-------|
| Cache condicional | [`cache/conditional_payload.py`](infra/cache/conditional_payload.py) | ETag / Last-Modified / resposta 304 |
| Singleflight | [`cache/singleflight.py`](infra/cache/singleflight.py) | Coalesce de requisições paralelas à mesma URL |
| Robots | [`infra/robots.py`](infra/robots.py) | Validação de robots.txt com cache Redis por domínio |
| `AdaptiveRateLimiter` | [`limits/adaptive_rate_limiter.py`](infra/limits/adaptive_rate_limiter.py) | Cooldown por domínio baseado em histórico de erros |
| `StructuredLogger` | [`logging/structured_logger.py`](infra/logging/structured_logger.py) | Logger com contexto obrigatório (`trace_id`, `domain`, etapa) |
| `COLLECTION_ERROR_MAP` | [`errors_map.py`](infra/errors_map.py) | Taxonomia interna → (`error_code`, mensagem, `http_status`) |
| `CACHE_INVALIDATING_ERROR_CODES` | [`errors_map.py`](infra/errors_map.py) | Erros de conteúdo que invalidam cache (ex.: `anti_bot_page`) |

---

## Telemetria

Cada execução do pipeline emite eventos estruturados via `TelemetryService`, sempre com `trace_id` e `domain` no contexto de log.

### Eventos em Ordem de Execução

| Evento | Campos principais |
|--------|-------------------|
| `collection_started` | `url` |
| `collection_completed` | `layer`, `duration_ms`, `fallback_taken`, `anti_bot_detected`, `http_status`, `runtime`, `classification_reason` |
| `extraction_started` | — |
| `extraction_completed` | `parser_used`, `duration_ms`, `succeeded` |
| `post_processing_started` | — |
| `post_processing_completed` | `duration_ms`, `has_price`, `availability` |
| `pipeline_completed` | `outcome`, `total_duration_ms` |

### Rastreio por `trace_id`

O `trace_id` é gerado na rota e propagado via `structlog.contextvars` por todo o pipeline. Todos os eventos e logs carregam o mesmo `trace_id`:

```bash
# Filtrar todos os logs de uma requisição específica
docker logs market_scraper 2>&1 | grep '"trace_id": "abc-123"'
```

A telemetria de aquisição é consolidada em `PostProcessResult.extra_fields["acquisition"]` e propagada na `ParserResponse.payload` para auditoria pelo consumidor.

---

## Configuração

Variáveis de ambiente controladas em [`core/config_scraper.py`](core/config_scraper.py).

---

## Como Estender

### Adicionar um novo parser de extração

1. Criar `extraction/parsers/meu_parser.py` com a assinatura:
   ```python
   def parse_with_meu_parser(html: str, url: str) -> dict | None: ...
   ```
2. Registrar em [`extraction/parsers/__init__.py`](extraction/parsers/__init__.py).
3. Inserir na lista `_STEPS` de [`extraction/extraction_chain.py`](extraction/extraction_chain.py) na posição desejada da cadeia.

### Modificar a política de coleta

A decisão `ACCEPT / ESCALATE_TO_BROWSER / STOP_UNAVAILABLE / STOP_FAILURE` é centralizada em [`collection/policy.py`](collection/policy.py) — método `ResponseClassifierPolicy.classify()`. Ajustar limiares de status HTTP ou padrões anti-bot apenas aqui; `CrawleeRuntime` e `ParseProduct` não precisam mudar.

### Adicionar um normalizer de pós-processamento

1. Criar `post_processing/normalizers/meu_normalizer.py`.
2. Chamar no [`post_processing/processor.py`](post_processing/processor.py) dentro de `PostProcessor.run()`.
3. Dados adicionais vão para `PostProcessResult.extra_fields`; substituições de campos canônicos atualizam `name`, `current_price`, `availability`, etc.

### Suportar um novo domínio de e-commerce

Parsers específicos de domínio ficam dentro dos parsers genéricos, condicionados ao `source` (domínio extraído da URL):
1. Adicionar seletores CSS/XPath específicos em [`extraction/parsers/parsel.py`](extraction/parsers/parsel.py) ou [`beautifulsoup.py`](extraction/parsers/beautifulsoup.py).
2. Validar com fixtures HTML em `tests/unit/` e cobrir com teste de integração em `tests/integration/`.

---

## Operação e Troubleshooting

### Rodar testes

```bash
cd backend/market_scraper
python -m pytest tests/ -q              # Suite completa
python -m pytest tests/unit/ -q         # Somente unitários
python -m pytest tests/integration/ -q  # Somente integração
python -m pytest tests/ --tb=short -q   # Com detalhe em falhas
```

### Iniciar o serviço localmente

```bash
cd backend
uvicorn market_scraper.main:app --reload --port 8001
```

### Logs — Eventos Principais

| Evento de log | Significado | Ação recomendada |
|---------------|-------------|-----------------|
| `playwright_pool_startup_failed` | Browser pool não iniciou; HTTP continua disponível | Verificar instalação do Playwright (`playwright install chromium`) |
| `collection_completed` com `fallback_taken=true` | HTTP falhou e browser foi acionado | Normal em sites com proteção anti-bot |
| `parse_no_result` | Nenhum parser extraiu dados úteis | Verificar se o HTML retornado contém a página do produto |
| `rate_limiter_cooldown` | Domínio em cooldown por erros consecutivos | Aguardar cooldown ou revisar frequência de coleta |
| `browser_handler_orphan` | Handler do Crawlee chegou após o budget externo já ter expirado — anomalia operacional | Investigar se SCRAPER_BROWSER_BUDGET_SECONDS está muito próximo de SCRAPER_BROWSER_NAVIGATION_TIMEOUT_SECONDS |
| `robots_disallowed` | URL bloqueada por robots.txt | Em modo `audit` é log; em modo `block` retorna 403 |
| `use_case_completed` | Pipeline concluído com sucesso | Monitorar `duration_collect_ms`, `duration_extract_ms` |

### Debug de Falhas

1. **Obter `trace_id`** do campo `trace_id` na resposta de erro JSON.
2. **Filtrar logs** pelo `trace_id` para ver toda a sequência de eventos da requisição.
3. **Inspecionar `payload.acquisition`** na `ParserResponse` para identificar qual camada falhou.
4. **Forçar nova coleta** com `"force_refresh": true` dentro do campo `metadata` da request para ignorar cache.

### Alertas Recomendados

| Métrica | Limiar sugerido | Causa provável |
|---------|-----------------|----------------|
| Taxa `422 no_result` | > 10% | Mudança de layout no e-commerce alvo |
| Taxa `429 anti_bot` | > 5% | Aumento de detecção; revisar proxy ativo e política de sessão |
| Taxa `503 pipeline_degraded` | > 1% | Problema no browser pool; verificar Playwright |
| Taxa `anti_bot_blocked` | > 5% | Bloqueio terminal por IP/identidade; ativar ou rotacionar proxy |
| Frequência `browser_handler_orphan` | crescente | Budget externo e timeout de navegação desalinhados; revisar SCRAPER_BROWSER_BUDGET_SECONDS |
| Latência P95 | > 40s | Budget de browser sendo consumido sistematicamente |
