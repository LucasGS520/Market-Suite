# Market Scraper
Serviço FastAPI responsável por transformar URLs de marketplaces em um `ParseResponse` enxuto (`name`, `current_price`, `url`, `source`, `payload opcional`). O foco atual é estabilidade com páginas HTML estáticas, sem renderização de JavaScript. O `market_alert` consome este serviço via HTTP e nunca replica regras de parsing.

## Relações e Referências
- Visão arquitetural completa: [`../README.md`](../README.md)
- Orquestrador e consumo da API: [`../market_alert/README.md`](../market_alert/README.md)

## Endpoints
| Método | Rota | Descrição |
|--------|------|-----------|
| `POST` | `/scraper/parse` (alias `/scrape/parse`) | Recebe `ParseRequest`, executa o pipeline e devolve `ParseResponse`. Pode retornar `304 Not Modified` ou `no_result` quando não há dados novos. |
| `GET` | `/health/ping` | Retorna `{ "status": "ok" }` para monitoramento básico. |
| `GET` | `/metrics` | Exibe métricas Prometheus do `REGISTRY` padrão. |

O cliente oficial vive em [`market_alert/services/scraper_client.py`](../market_alert/services/scraper_client.py) e encapsula autenticação, timeouts e tratamento dos códigos de resposta.

## Pipeline de Parsing
O pipeline sequencial é registrado em [`services/pipeline_steps.py`](services/pipeline_steps.py) e executado pelo `SynergicPipeline` (`services/synergic_pipeline.py`). Ordem padrão:

1. **FetchHTMLStep** – normaliza URL, verifica `robots.txt`, consulta cache LRU/TTL e singleflight antes de baixar HTML via `httpx` com retries leves.
2. **DomainSpecificParserStep** – ativa parsers dedicados (`parsers/domain_parsers.py`) quando o domínio possui regras especializadas.
3. **JsonLdParserStep** – procura dados estruturados `application/ld+json`.
4. **HtmlMetadataParserStep** – coleta metadados e marcações estruturais com BeautifulSoup.
5. **GenericFallbackParserStep** – aplica heurísticas genéricas (`price-parser` + regras textuais) quando etapas anteriores falham.

Tempo máximo por etapa: `SCRAPER_STEP_TIMEOUT_SECONDS`. Tempo total do pipeline: `SCRAPER_PIPELINE_TIMEOUT_SECONDS`. Métricas obrigatórias são registradas via `shared/metrics/metrics_scraper.py` (`SCRAPER_STEP_*`, `SCRAPER_NO_RESULT_TOTAL`, `SCRAPING_LATENCY_SECONDS`).

## Configuração
As variáveis padrão estão em [`core/config_scraper.py`](core/config_scraper.py) e podem ser sobrescritas via `market_scraper/.env.market_scraper`.

| Categoria | Variáveis relevantes |
|-----------|---------------------|
| Timeouts | `SCRAPER_STEP_TIMEOUT_SECONDS`, `SCRAPER_PIPELINE_TIMEOUT_SECONDS`, `SCRAPER_HTTP_TIMEOUT_*`, `SCRAPER_DNS_TIMEOUT` |
| HTTP | `SCRAPER_HTTP_RETRIES`, `SCRAPER_HTTP_RETRY_BACKOFF_BASE`, `SCRAPER_HTTP_MAX_*`, `SCRAPER_DEFAULT_USER_AGENT`, `SCRAPER_USER_AGENT_POOL`, `SCRAPER_HEADERS_*` |
| Cache | `SCRAPER_CACHE_TTL_SECONDS`, `SCRAPER_CACHE_MAX_ENTRIES`, `SCRAPER_SINGLEFLIGHT_LOCK_TTL` |
| Parsing | `SCRAPER_PRICE_TOLERANCE`, flags de domínio em `parsers/` e parâmetros adicionais documentados no código |

## Principais Componentes
- `services/parser_runner.py` – executa parsers e aplica validação de dados.
- `utils/url_validation.py` – lista domínios suportados e bloqueia hosts privados.
- `utils/http_utils.py` – resolve DNS com cache e impede SSRF.
- `utils/http_download.py` – baixa HTML aplicando user agent, retries (`utils/http_retry.py`) e limites configuráveis.
- `utils/cache.py` – cache LRU/TTL com métricas (`SCRAPER_CACHE_*`).
- `utils/robots.py` – consulta `robots.txt` com fallback permissivo e expõe métricas `SCRAPER_ROBOTS_CHECK_TOTAL`.
- `utils/singleflight.py` – coalescing para evitar downloads simultâneos.
- `utils/price.py` – heurísticas de preço com `price-parser` e fallback manual.

Exemplo mínimo de `.env.market_scraper`:
```env
# Configurações essenciais — mantêm o pipeline padrão previsível
SCRAPER_CACHE_TTL_SECONDS=3600
SCRAPER_CACHE_MAX_ENTRIES=5000

SCRAPER_STEP_TIMEOUT_SECONDS=8.0
SCRAPER_PIPELINE_TIMEOUT_SECONDS=20.0

SCRAPER_HTTP_RETRIES=2
SCRAPER_HTTP_RETRY_BACKOFF_BASE=0.5

SCRAPER_SINGLEFLIGHT_LOCK_TTL=15.0

```

## Segurança e Salvaguardas
- **Validação de domínio:** apenas marketplaces documentados em `utils/url_validation.py` são aceitos; requisições inválidas retornam `400`.
- **Proteção contra SSRF:** `utils/http_utils.py` bloqueia IPs privados/loopback e reutiliza DNS com TTL configurável (`SCRAPER_DNS_CACHE_TTL`).
- **Robots.txt permissivo:** caso o arquivo não possa ser carregado, aplicamos fallback `allow` documentado no próprio módulo para manter disponibilidade. Bloqueios explícitos retornam `unsupported_by_robots`.
- **Cache defensivo:** itens são invalidados por TTL e capacidade. Métricas `SCRAPER_CACHE_LOOKUPS_TOTAL`, `SCRAPER_CACHE_HIT_RATE`, `SCRAPER_CACHE_EVICTIONS_TOTAL` auxiliam na calibração.

## Observabilidade
- Métricas Prometheus em `/metrics` (`SCRAPER_STEP_LATENCY_SECONDS`, `SCRAPER_HTTP_RETRIES_TOTAL`, `SCRAPER_DNS_RESOLVE_DURATION_SECONDS`, etc.).
- Logs estruturados do pipeline (`logger` em `services/synergic_pipeline.py`) descrevem etapa, domínio, resultado e duração.
- Health-check simples em `/health/ping` facilita probes do docker-compose ou orquestradores.

## Execução Local
- **Docker Compose:** `docker compose up -d market_scraper` (depende de `redis`, `db` e variáveis de `.env.common`).
- **Sem Docker:**
  1. Ative a virtualenv e instale dependências (`pip install -r ../requirements.txt`).
  2. Configure `.env.common` e `.env.market_scraper`.
  3. Execute `uvicorn market_scraper.main:app --reload --port 8010`.

## Testes
```bash
pytest market_scraper -q
```
As suítes incluem fixtures para respostas HTTP, validação de URL, DNS protegido, robots e cache. Execute módulos específicos com `pytest market_scraper/tests/<módulo> -k <nome>`.

## Recursos Legados
- `archive/domain_policy.py` e `archive/domain_policy.yaml` preservam a abordagem antiga baseada em políticas externas. Só reintroduza mediante requisito formal e atualize este README + `AGENTS.md`.
- Outros componentes arquivados devem permanecer inativos até nova decisão do time.

## Troubleshooting rápido
- **`unsupported_by_robots` frequente:** revise logs de `utils/robots.py` e confirme se o domínio realmente permite scraping. Mudanças conservadoras exigem revisão do runbook documentado no módulo.
- **`304 Not Modified` constante:** ajuste `SCRAPER_CACHE_TTL_SECONDS` ou limpe o cache via `utils/cache.clear()` em ambiente controlado.
- **Falhas DNS recorrentes:** aumente `SCRAPER_DNS_TIMEOUT` temporariamente e monitore `SCRAPER_DNS_BLOCKED_TOTAL`.

Atualize este documento sempre que etapas do pipeline, domínios suportados ou métricas forem alterados.
