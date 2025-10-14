# Market Scraper

## Objetivo
O serviço `market_scraper` coleta nome e preço de anúncios em marketplaces estáticos. A implementação atual prioriza confiabilidade e baixo tempo de resposta, utilizando apenas páginas HTML e metadados expostos sem renderização de JavaScript.

## Endpoints principais
- `POST /scraper/parse` (alias `POST /scrape/parse`): recebe `{ "url": "<string>" }` e devolve `ParserResponse` com `name`, `current_price`, `url` e `source`.
- `GET /health/ping`: verificação simples de disponibilidade.
- `GET /metrics`: expõe as métricas registradas no `prometheus_client`.

## Pipeline mínimo
O fluxo é sequencial e definido em `market_scraper/services/pipeline_steps.py`:

1. **FetchHTMLStep** – valida `robots.txt`, bloqueia SSRF (hosts privados) e baixa o HTML com `httpx`. Ao sucesso, o HTML é salvo no contexto compartilhado e no cache.
2. **JsonLdParserStep** – tenta extrair dados estruturados (`application/ld+json`).
3. **HtmlMetadataParserStep** – analisa metatags e elementos semânticos com BeautifulSoup.
4. **GenericFallbackParserStep** – aplica heurísticas genéricas no HTML para obter nome e preço.

Cada etapa registra métricas de latência e resultado (`success`, `empty`, `failure`). O pipeline completo respeita `SCRAPER_STEP_TIMEOUT_SECONDS` por etapa e `SCRAPER_PIPELINE_TIMEOUT_SECONDS` como teto global.

## Validação de URLs e segurança
- Apenas marketplaces listados em `market_scraper/utils/url_validation.py` são aceitos (Mercado Livre, Amazon Brasil e Magazine Luiza).
- O módulo `market_scraper/utils/http_utils.py` evita SSRF resolvendo o host para endereços públicos e recusando IPs privados/loopback.
- O utilitário `market_scraper/utils/robots.py` reutiliza `robots.txt` por host durante uma hora. Se o site negar acesso, a etapa `FetchHTMLStep` retorna `unsupported_by_robots`.

## Cache básico
O cache padrão utiliza um dicionário em memória protegido por lock (`market_scraper/utils/cache.py`). Principais características:

- Controlado por `SCRAPER_CACHE_ENABLED` (habilitado por padrão) e TTL configurado por `SCRAPER_CACHE_TTL_SECONDS`.
- Métricas: `SCRAPER_CACHE_LOOKUPS_TOTAL` (hits/misses) e `SCRAPER_CACHE_SIZE` (entradas em memória).
- Para ambientes com Redis, defina `SCRAPER_CACHE_BACKEND=redis` e configure `REDIS_HOST`, `REDIS_PORT`, `REDIS_DB` e `REDIS_PASSWORD` no `.env.common` ou `.env.market_scraper`. O backend `redis` permanece reservado para quando o adaptador dedicado for reativado; mantenha `memory` enquanto essa integração estiver indisponível.

## Configurações relevantes (`market_scraper/core/config_scraper.py`)
- `SCRAPER_STEP_TIMEOUT_SECONDS` / `SCRAPER_PIPELINE_TIMEOUT_SECONDS` – limites de tempo do pipeline.
- `SCRAPER_HTTP_TIMEOUT_CONNECT`, `SCRAPER_HTTP_TIMEOUT_READ`, `SCRAPER_HTTP_TIMEOUT_WRITE`, `SCRAPER_HTTP_TIMEOUT_POOL` – controle fino de timeouts `httpx`.
- `SCRAPER_HTTP_MAX_REDIRECTS`, `SCRAPER_HTTP_MAX_CONNECTIONS`, `SCRAPER_HTTP_MAX_KEEPALIVE`, `SCRAPER_HTTP_MAX_CONTENT_LENGTH` – limites defensivos.
- `SCRAPER_CACHE_ENABLED`, `SCRAPER_CACHE_TTL_SECONDS`, `SCRAPER_CACHE_BACKEND`, `SCRAPER_CACHE_MAX_ENTRIES`, `SCRAPER_CACHE_EVICTION_POLICY` - configuração detalhada do cache em memória ou Redis.
- `SCRAPER_HTTP_RETRIES`, `SCRAPER_HTTP_RETRY_BACKOFF_BASE` - controle de novas tentativas com backoff exponencial leve para downloads.
- `SCRAPER_ROBOTS_FALLBACK` - define a política padrão quando o robots parser falha (`allow` ou `block`).
- `SCRAPER_DNS_TIMEOUT` - timeout máximo para resolução DNS.
- `SCRAPER_DNS_CACHE_TTL` - tempo em segundos que uma resolução DNS permanece em cache.
- `SCRAPER_USE_PRICE_PARSER`, `SCRAPER_SINGLEFLIGHT_ENABLED` - flags para novas estratégias do pipeline.
- `SCRAPER_SINGLEFLIGHT_LOCK_TTL` - TTL dos locks do singleflight para reciclar entradas travadas.
- Demais variáveis herdadas de `shared.core.config_base.ConfigBase` (Redis, observabilidade, etc.) são definidas em `.env.common`.

### Arquivo `.env.market_scraper`
Use este arquivo para sobrescrever valores padrão. Exemplo:

```env
REDIS_HOST=redis
REDIS_PORT=6379
REDIS_DB=0
REDIS_PASSWORD=

#Backend e limites de Cache básico por URL
SCRAPER_CACHE_ENABLED=1
SCRAPER_CACHE_BACKEND=memory
SCRAPER_CACHE_TTL_SECONDS=3600
SCRAPER_CACHE_MAX_ENTRIES=5000
SCRAPER_CACHE_ENVICTION_POLICY=lru

#Estratégias de robots.txt e fallback seguro
SCRAPER_ROBOTS_FALLBACK=allow

#Controle de tentativas HTTP e backoff
SCRAPER_HTTP_RETRIES=2
SCRAPER_HTTP_RETRY_BACKOFF_BASE=0.5

SCRAPER_STEP_TIMEOUT_SECONDS=8.0
SCRAPER_PIPELINE_TIMEOUT_SECONDS=20.0

#Timeout de resolução DNS para evitar bloqueios longos
SCRAPER_DNS_TIMEOUT=2
SCRAPER_DNS_CACHE_TTL=120

#Estratégias opcionais do pipelie
SCRAPER_USE_PRICE_PARSER=0
SCRAPER_SINGLEFLIGHT_ENABLED=1
SCRAPER_SINGLEFLIGHT_LOCK_TTL=15.0

# Limites HTTP defensivos
SCRAPER_HTTP_MAX_REDIRECTS=3
SCRAPER_HTTP_MAX_CONTENT_LENGTH=2000000
SCRAPER_HTTP_MAX_CONNECTIONS=10
SCRAPER_HTTP_MAX_KEEPALIVE=5

SCRAPER_HTTP_TIMEOUT_CONNECT=3.0
SCRAPER_HTTP_TIMEOUT_READ=3.0
SCRAPER_HTTP_TIMEOUT_WRITE=3.0
SCRAPER_HTTP_TIMEOUT_POOL=3.0
```

## Métricas expostas
As métricas estão em `shared/metrics/metrics_scraper.py`. Destaques:

- `SCRAPER_STEP_SUCCESS_TOTAL`, `SCRAPER_STEP_FALLBACK_TOTAL` e `SCRAPER_STEP_INVALID_TOTAL` – contadores por etapa/resultado.
- `SCRAPER_STEP_LATENCY_SECONDS` – histograma de latência das etapas do pipeline.
- `SCRAPER_NO_RESULT_TOTAL` – contagem de execuções que terminaram sem payload válido.
- `SCRAPING_LATENCY_SECONDS` – histograma de latência agregado por fonte.
- `SCRAPER_ROBOTS_CHECK_TOTAL` – contagem de checagens de robots (`allowed`, `disallowed`, `error`).
- `SCRAPER_SINGLEFLIGHT_CALLS_TOTAL`, `SCRAPER_SINGLEFLIGHT_WAIT_SECONDS` - acompanham coalescing de downloads e tempo de espera.
- Métricas de cache listadas acima.

Para visualizar, acesse `GET /metrics` ou configure o Prometheus via `docker-compose`.

## Execução local
```bash
uvicorn market_scraper.main:app --port 8010 --reload
```

Opcionalmente, utilize Docker (`docker compose up market_scraper`). Garanta que `.env.common` e `market_scraper/.env.market_scraper` estejam configurados antes de iniciar.

## Testes
Execute os testes dedicados ao scraper:

```bash
pytest market_scraper -q
```

O pacote inclui fixtures para simular Redis, respostas HTTP e HTML de marketplaces.

## Recursos arquivados
- `market_scraper/archive/domain_policy.py` e `market_scraper/archive/domain_policy.yaml` preservam a versão antiga baseada em políticas declarativas. Para reativá-la, mova os arquivos para `market_scraper/services/`, atualize os imports e reintroduza o carregamento dinâmico antes de registrar as etapas no pipeline.
- Outros componentes legados removidos do fluxo mínimo devem permanecer arquivados até que haja um requisito explícito para retomá-los.

## Próximos passos
- Implementar backend Redis definitivo para o cache de HTML.
- Expandir a lista de marketplaces suportados conforme novas regras forem consolidadas.