# Market Scraper
Serviço FastAPI responsável por transformar URLs de marketplaces em um `ParseResponse` enxuto (`name`, `current_price`, `url`, `source`, `payload opcional`). O foco atual é estabilidade com páginas HTML estáticas, sem renderização de JavaScript. O `market_alert` consome este serviço via HTTP e nunca replica regras de parsing.

## Relações e Referências
- Visão arquitetural completa da suíte: [`../README.md`](../README.md)
- API orquestradora e consumo oficial: [`../market_alert/README.md`](../market_alert/README.md)
- Guia operacional para agentes: [`../AGENTS.md`](../AGENTS.md)

## Principais Responsabilidades
- **Normalizar e validar URLs** aceitando apenas marketplaces suportados.
- **Executar pipeline de scraping** com etapas específicas por domínio, metadados e fallback genérico.
- **Expor API REST** para consumo síncrono (`/scraper/parse`) e endpoints de suporte (`/health/ping`, `/metrics`).
- **Registrar métricas detalhadas** de latência, cache, DNS e resultados de parsing.

## Estrutura do Diretório
```text
market_scraper/
├── core/                 #Configuração do serviço, carregamento de env e inicialização FastAPI
├── main.py               #Criação da aplicação FastAPI, middlewares e rotas
├── routes/               #Rotas públicas (/scraper/parse, /health, /metrics)
├── services/             #Pipeline, etapas e orquestradores de parsing
├── parsers/              #Parsers específicos por domínio e fallback genérico
├── utils/                #Utilidades (HTTP, cache, DNS, robots, validação de URL)
├── schemas/              #Modelos de erro locais
└── tests/                #Suite de testes do serviço
```

## Endpoints e Fluxos Relevantes
| Método | Rota / Fluxo | Descrição |
|--------|--------------|-----------|
| `POST` | `/scraper/parse` | Recebe `ParserRequest`, executa o pipeline e devolve `ParserResponse`. Pode retornar `304 Not Modified` ou `no_result` quando não há dados novos. |
| `GET` | `/health/ping` | Retorna `{ "status": "ok" }` para monitoramento básico. |
| `GET` | `/metrics` | Exibe métricas Prometheus do `REGISTRY` padrão. |
| `Pipeline` | `services/synergic_pipeline.SynergicPipeline` | Coordena etapas sequenciais de parsing com timeouts individuais. |
| `Pipeline` | `services/pipeline_steps.FetchHTMLStep` | Baixa HTML aplicando cache, singleflight e política de robots. |

O cliente oficial vive em [`market_alert/scraper/scraper_client.py`](../market_alert/services/scraper_client.py) e encapsula autenticação, timeouts, tratamento de `304 Not Modified` e validação do contrato compartilhado.

### Integração com os Serviços
- **`market_alert`**: consome o endpoint `/scraper/parse` via `ScraperClient`, usando autenticação e timeouts definidos na API.
- **`shared/`**: reaproveita métricas (`shared/metrics/metrics_scraper.py`), utilidades de configuração e padrões de logs.
- **Infraestrutura compartilhada**: depende de Redis para cache opcional, utiliza `.env.common` para parâmetros globais e compartilha observabilidade via Prometheus/Loki definidos no `docker-compose.yml`.

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
| HTTP | `SCRAPER_HTTP_RETRIES`, `SCRAPER_HTTP_RETRY_BACKOFF_BASE`, `SCRAPER_DEFAULT_USER_AGENT`, `SCRAPER_USER_AGENT_POOL`, `SCRAPER_HEADERS_*` |
| Cache | `SCRAPER_CACHE_TTL_SECONDS`, `SCRAPER_CACHE_MAX_ENTRIES`, `SCRAPER_SINGLEFLIGHT_LOCK_TTL` |
| Parsing | `SCRAPER_PRICE_TOLERANCE`, `SCRAPER_ALLOWED_DOMAINS`, flags em `parsers/` |
| Observabilidade | `SERVICE_NAME`, `OTEL_EXPORTER_OTLP_ENDPOINT`, `METRICS_PORT`, `LOG_LEVEL` |

## Principais Componentes do Serviço
- `services/synergic_pipeline.py` – organiza execução do pipeline, métricas e tratamento de exceções.
- `services/pipeline_steps.py` – lista etapas (`FetchHTMLStep`, `DomainSpecificParserStep`, `JsonLdParserStep`, `HtmlMetadataParserStep`, `GenericFallbackParserStep`).
- `services/parser_runner.py` – valida dados extraídos e gera `ParserResponse` final.
- `utils/http_utils.py` – resolve DNS com cache e previne SSRF.
- `utils/http_download.py` – realiza download com retries configuráveis.
- `utils/cache.py` – implementa cache LRU/TTL e métricas associadas.
- `utils/robots.py` – consulta `robots.txt` respeitando bloqueios explícitos.
- `shared/utils/url_validation.py` – validação de domínio, esquema e normalização de URLs utilizada por ambos os serviços.

Exemplo mínimo de `.env.market_scraper`:
```env
SCRAPER_CACHE_TTL_SECONDS=3600
SCRAPER_CACHE_MAX_ENTRIES=5000
SCRAPER_SINGLEFLIGHT_LOCK_TTL=15.0

SCRAPER_STEP_TIMEOUT_SECONDS=8.0
SCRAPER_PIPELINE_TIMEOUT_SECONDS=20.0

SCRAPER_HTTP_RETRIES=2
SCRAPER_HTTP_RETRY_BACKOFF_BASE=0.5

SERVICE_NAME=market-scraper
```

## Segurança e Observabilidade
- **Segurança:**
  - Validação de domínio apenas marketplaces documentados em `shared/utils/url_validation.py` são aceitos; requisições inválidas retornam `400`.
  - Proteção contra SSRF `utils/http_utils.py` bloqueia IPs privados/loopback e reutiliza DNS com TTL configurável (`SCRAPER_DNS_CACHE_TTL`).
  - Robots.txt permissivo caso o arquivo não possa ser carregado, aplicamos fallback `allow` documentado no próprio módulo para manter disponibilidade. Bloqueios explícitos retornam `unsupported_by_robots`.
  - Cache defensivo itens são invalidados por TTL e capacidade. Métricas `SCRAPER_CACHE_LOOKUPS_TOTAL`, `SCRAPER_CACHE_HIT_RATE`, `SCRAPER_CACHE_EVICTIONS_TOTAL` auxiliam na calibração.

- **Observabilidade:**
  - Métricas detalhadas em `/metrics` (`SCRAPER_STEP_LATENCY_SECONDS`, `SCRAPER_HTTP_RETRIES_TOTAL`, `SCRAPER_DNS_RESOLVE_DURATION_SECONDS`, `SCRAPER_CACHE_*`)
  - Logs estruturados do pipeline (`logger` em `services/synergic_pipeline.py`) descrevem etapa, domínio, resultado e duração.
  - Health-check simples em `/health/ping` facilita probes do docker-compose ou orquestradores.

## Execução Local
- **Docker Compose (recomendado):**
  ```bash
  docker compose up -d market_scraper
  ```
  O serviço depende de `redis`, `db` e variáveis definidas em `.env.common`.

- **Sem Docker:**
  1. Ative virtualenv e instale dependências: `pip install -r ../requirements.txt`.
  2. Configure `.env.common` e `.env.market_scraper`.
  3. Inicie a API: `uvicorn market_scraper.main:app --reload --port 8010`.

## Testes
```bash
pytest market_scraper -q
```
A suíte cobre pipeline, parsers específicos, validação de URLs, cache, DNS, robots e integrações HTTP simuladas. Utilize `pytest market_scraper/tests/<módulo> -k <termo>` para focar cenários.

## Recursos Legados
- Implementações antigas baseadas em `domain_policy` foram removidas do código ativo. Caso surja a necessidade de reavaliar políticas externas por domínio, consulte o histórico do repositório antes de reinstalar qualquer dependência.

## Troubleshooting rápido
- **`unsupported_by_robots` frequente**: revise logs de `utils/robots.py` e confirme permissões do domínio. Ajuste configurações apenas após validação legal.
- **`304 Not Modified` constante**: reduza `SCRAPER_CACHE_TTL_SECONDS` ou limpe cache via `utils/cache.clear()` em ambiente controlado.
- **Falhas DNS recorrentes**: aumente `SCRAPER_DNS_TIMEOUT` temporariamente e monitore `SCRAPER_DNS_BLOCKED_TOTAL`.
- **Latência elevada**: avalie métricas `SCRAPER_STEP_LATENCY_SECONDS` para identificar etapa crítica e ajuste timeouts ou heurísticas.

Atualize este documento sempre que etapas do pipeline, domínios suportados ou métricas forem alterados.
