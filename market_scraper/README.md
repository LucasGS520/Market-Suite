# Market Scraper

## Objetivo
O serviço `market_scraper` coleta nome e preço de anúncios em marketplaces estáticos. A implementação atual prioriza confiabilidade e baixo tempo de resposta, utilizando apenas páginas HTML e metadados expostos sem renderização de JavaScript.

## Endpoints principais
- `POST /scraper/parse` (alias `POST /scrape/parse`): recebe `{ "url": "<string>" }` e devolve `ParserResponse` com `name`, `current_price`, `url` e `source`.
- `GET /health/ping`: verificação simples de disponibilidade.
- `GET /metrics`: expõe as métricas registradas no `prometheus_client`.

## Pipeline mínimo
O fluxo é sequencial e definido em `market_scraper/services/pipeline_steps.py`:

1. **FetchHTMLStep** – normaliza a URL, consulta o singleflight para evitar downloads duplicados, valida `robots.txt`, bloqueia SSRF (hosts privados) e baixa o HTML com `httpx` usando retries com backoff. Ao sucesso, o HTML é salvo no contexto compartilhado e no cache configurado.
2. **JsonLdParserStep** – tenta extrair dados estruturados (`application/ld+json`).
3. **HtmlMetadataParserStep** – analisa metatags e elementos semânticos com BeautifulSoup.
4. **GenericFallbackParserStep** – aplica heurísticas genéricas no HTML para obter nome e preço, utilizando `price-parser` como primeira estratégia textual.

Cada etapa registra métricas de latência e resultado (`success`, `empty`, `failure`). O pipeline completo respeita `SCRAPER_STEP_TIMEOUT_SECONDS` por etapa e `SCRAPER_PIPELINE_TIMEOUT_SECONDS` como teto global. Retries adicionais seguem `SCRAPER_HTTP_RETRIES` e `SCRAPER_HTTP_RETRY_BACKOFF_BASE`, aplicando o cabeçalho `Retry-After` sempre que presente.

## Validação de URLs e segurança
- Apenas marketplaces listados em `market_scraper/utils/url_validation.py` são aceitos (Mercado Livre, Amazon Brasil e Magazine Luiza).
- O módulo `market_scraper/utils/http_utils.py` evita SSRF resolvendo o host para endereços públicos, recusando IPs privados/loopback e aplicando cache com TTL e timeout configuráveis (`SCRAPER_DNS_CACHE_TTL`, `SCRAPER_DNS_TIMEOUT`). Métricas acompanham resoluções bem-sucedidas, bloqueios e falhas (`SCRAPER_DNS_RESOLVE_DURATION_SECONDS`, `SCRAPER_DNS_BLOCKED_TOTAL`).
- O utilitário `market_scraper/utils/robots.py` reutiliza `robots.txt` por host durante uma hora, aplica retries com backoff e, diante de falhas de download ou parse, adota fallback permissivo documentado. Se o site negar acesso explicitamente, a etapa `FetchHTMLStep` retorna `unsupported_by_robots` e incrementa `SCRAPER_ROBOTS_CHECK_TOTAL` com o label `disallowed`.

## Cache resiliente
O cache padrão utiliza `cachetools.TTLCache` com bloqueios internos (`market_scraper/utils/cache.py`). Principais características:

- O cache em memória com LRU/TTL é utilizado sempre e respeita o TTL configurado por `SCRAPER_CACHE_TTL_SECONDS`.
- O limite máximo de entradas (`SCRAPER_CACHE_MAX_ENTRIES`) mantém política LRU e suporte a TTL individual por item. Evictions são contabilizadas em `SCRAPER_CACHE_EVICTIONS_TOTAL` e o tamanho atual em `SCRAPER_CACHE_SIZE`.
- Métricas de hits/misses são atualizadas em `SCRAPER_CACHE_LOOKUPS_TOTAL` e `SCRAPER_CACHE_HIT_RATE`.

## Camada de utilitários reforçada
- **Retries HTTP** (`market_scraper/utils/http_retry.py`): centraliza tentativas extras para downloads de HTML e `robots.txt`, respeitando `Retry-After`, aplicando backoff exponencial e registrando métricas (`SCRAPER_HTTP_RETRIES_TOTAL`, `SCRAPER_HTTP_RETRY_BACKOFF_SECONDS`).
- **Singleflight** (`market_scraper/utils/singleflight.py`): reduz stampede de downloads concorrentes agrupando chamadas por URL, com métricas de espera e participação sempre ativas.
- **DNS seguro** (`market_scraper/utils/http_utils.py`): restringe IPs privados, reutiliza resoluções em cache e falha rapidamente quando o host não é público.
- **Parsing de preço** (`market_scraper/utils/price.py`): utiliza o `price-parser` como primeira estratégia e mantém fallback manual, contabilizando resultados em `SCRAPER_PRICE_PARSER_USAGE_TOTAL`.
- **Robots permissivo** (`market_scraper/utils/robots.py`): utiliza apenas `urllib.robotparser`, mantém cache local com TTL e fallback permissivo quando o arquivo não é acessível.

## Configurações relevantes (`market_scraper/core/config_scraper.py`)
- `SCRAPER_STEP_TIMEOUT_SECONDS` / `SCRAPER_PIPELINE_TIMEOUT_SECONDS` – limites de tempo do pipeline.
- `SCRAPER_HTTP_TIMEOUT_CONNECT`, `SCRAPER_HTTP_TIMEOUT_READ`, `SCRAPER_HTTP_TIMEOUT_WRITE`, `SCRAPER_HTTP_TIMEOUT_POOL` – controle fino de timeouts `httpx`.
- `SCRAPER_HTTP_MAX_REDIRECTS`, `SCRAPER_HTTP_MAX_CONNECTIONS`, `SCRAPER_HTTP_MAX_KEEPALIVE`, `SCRAPER_HTTP_MAX_CONTENT_LENGTH` – limites defensivos.
- `SCRAPER_CACHE_TTL_SECONDS`, `SCRAPER_CACHE_MAX_ENTRIES` - controle do cache em memória com LRU/TTL.
- `SCRAPER_HTTP_RETRIES`, `SCRAPER_HTTP_RETRY_BACKOFF_BASE` - controle de novas tentativas com backoff exponencial leve para downloads.
- `SCRAPER_DNS_TIMEOUT` - timeout máximo para resolução DNS.
- `SCRAPER_DNS_CACHE_TTL` - tempo em segundos que uma resolução DNS permanece em cache.
- `SCRAPER_SINGLEFLIGHT_LOCK_TTL` - TTL dos locks do singleflight para reciclar entradas travadas.
- `SCRAPER_PRICE_TOLERANCE` - tolerância percentual opcional para aceitar preços aproximados.
- Demais variáveis herdadas de `shared.core.config_base.ConfigBase` (Redis, observabilidade, etc.) são definidas em `.env.common`.

### Arquivo `.env.market_scraper`
Use este arquivo para sobrescrever valores padrão. Exemplo:

```env
# Configurações essenciais — mantêm o pipeline padrão previsível
SCRAPER_CACHE_TTL_SECONDS=3600
SCRAPER_CACHE_MAX_ENTRIES=5000

SCRAPER_STEP_TIMEOUT_SECONDS=8.0
SCRAPER_PIPELINE_TIMEOUT_SECONDS=20.0

SCRAPER_HTTP_RETRIES=2
SCRAPER_HTTP_RETRY_BACKOFF_BASE=0.5

SCRAPER_SINGLEFLIGHT_LOCK_TTL=15.0
SCRAPER_PRICE_TOLERANCE=0.0

# Ajustes de rede raramente necessários — mantenha comentado para seguir o padrão
#SCRAPER_HTTP_MAX_REDIRECTS=3
#SCRAPER_HTTP_MAX_CONTENT_LENGTH=2000000
#SCRAPER_HTTP_MAX_CONNECTIONS=10
#SCRAPER_HTTP_MAX_KEEPALIVE=5
#SCRAPER_HTTP_TIMEOUT_CONNECT=3.0
#SCRAPER_HTTP_TIMEOUT_READ=3.0
#SCRAPER_HTTP_TIMEOUT_WRITE=3.0
#SCRAPER_HTTP_TIMEOUT_POOL=3.0
#SCRAPER_DNS_TIMEOUT=2
#SCRAPER_DNS_CACHE_TTL=120
```

### Política de fallback do robots.txt
- Comportamento padrão: fallback permissivo (`allow`) quando `robots.txt` não pode ser obtido ou interpretado. Métrica `SCRAPER_ROBOTS_CHECK_TOTAL` registra o label `error` nesses casos.
- Justificativa: evita quedas em massa do pipeline quando sites retornam erros intermitentes ou bloqueiam a leitura do arquivo.
- Runbook para política conservadora (`block`):
  1. Ajustar `market_scraper/utils/robots.py` para retornar `False` nos blocos de fallback, conforme comentários do arquivo.
  2. Executar `pytest market_scraper/tests/unit/utils/test_robots.py` para validar as métricas e o novo comportamento.
  3. Gerar imagem/container atualizado, aplicar rollout gradual e monitorar `SCRAPER_ROBOTS_CHECK_TOTAL` (labels `disallowed` e `error`) por domínio.
  4. Se houver regressões relevantes, reverter o commit ou reinstaurar o fallback permissivo seguindo o mesmo fluxo.

## Métricas expostas
As métricas estão em `shared/metrics/metrics_scraper.py`. Destaques:

- `SCRAPER_STEP_SUCCESS_TOTAL`, `SCRAPER_STEP_FALLBACK_TOTAL` e `SCRAPER_STEP_INVALID_TOTAL` – contadores por etapa/resultado.
- `SCRAPER_STEP_LATENCY_SECONDS` – histograma de latência das etapas do pipeline.
- `SCRAPER_NO_RESULT_TOTAL` – contagem de execuções que terminaram sem payload válido.
- `SCRAPING_LATENCY_SECONDS` – histograma de latência agregado por fonte.
- `SCRAPER_ROBOTS_CHECK_TOTAL` – contagem de checagens de robots (`allowed`, `disallowed`, `error`).
- `SCRAPER_HTTP_RETRIES_TOTAL`, `SCRAPER_HTTP_RETRY_BACKOFF_SECONDS` – acompanham novas tentativas de download e tempo de espera aplicado.
- `SCRAPER_DNS_RESOLVE_DURATION_SECONDS`, `SCRAPER_DNS_BLOCKED_TOTAL` – observabilidade da camada DNS segura.
- `SCRAPER_SINGLEFLIGHT_CALLS_TOTAL`, `SCRAPER_SINGLEFLIGHT_WAIT_SECONDS` – acompanham coalescing de downloads e tempo de espera.
- `SCRAPER_PRICE_PARSER_USAGE_TOTAL` – monitora o uso do `price-parser` e cenários de fallback.
- Métricas de cache listadas acima (`SCRAPER_CACHE_LOOKUPS_TOTAL`, `SCRAPER_CACHE_HIT_RATE`, `SCRAPER_CACHE_EVICTIONS_TOTAL`, `SCRAPER_CACHE_SIZE`).

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

O pacote inclui fixtures para simular respostas HTTP e HTML de marketplaces.

## Recursos arquivados
- `market_scraper/archive/domain_policy.py` e `market_scraper/archive/domain_policy.yaml` preservam a versão antiga baseada em políticas declarativas. Para reativá-la, mova os arquivos para `market_scraper/services/`, atualize os imports e reintroduza o carregamento dinâmico antes de registrar as etapas no pipeline.
- Outros componentes legados removidos do fluxo mínimo devem permanecer arquivados até que haja um requisito explícito para retomá-los.

## Próximos passos
- Monitorar o comportamento do cache em memória e avaliar se um backend compartilhado será necessário futuramente.
- Expandir a lista de marketplaces suportados conforme novas regras forem consolidadas.