# Market Scraper
Serviço FastAPI responsavel por transformar URLs de produto em um `ParserResponse` enxuto (`name`, `current_price`, `currency`, `availability`, `last_status`, `url`, `source`, `payload`). Utiliza aquisição de HTML em cascata com TLS impersonation (curl_cffi) e fallback Playwright para páginas com JavaScript, atingindo alta taxa de sucesso em Mercado Livre e marketplaces similares. O `market_alert` consome este servico via HTTP e não replica regras de parsing.

## Relacoes e Referencias
- Visão arquitetural da suite: [`../README.md`](../README.md)
- API orquestradora e consumo oficial: [`../market_alert/README.md`](../market_alert/README.md)
- Orquestrador responsável pelo controle durável: [`../market_orchestrator/README.md`](../market_orchestrator/README.md)

## Principais Responsabilidades
- **Normalizar e validar URLs** (formato, esquema e host publico) antes de tentar scraping.
- **Adquirir HTML em cascata** (curl_cffi → Playwright) com classificação automática de resposta e rate limiting adaptativo.
- **Executar pipeline sequencial de parsing** com estrategia por etapas e parada no primeiro payload valido.
- **Expor API REST sincrona** para parse (`POST /scraper/parse`) e health check (`GET /health/ping`).
- **Aplicar cache HTTP condicional** com `ETag`/`Last-Modified` e suporte a `304 Not Modified`.

## Estrutura do Diretório
```text
market_scraper/
|-- core/                     # Configuracao do servico
|-- infra/                    # Infraestrutura de aquisição (rate limiter adaptativo)
|-- main.py                   # Bootstrap FastAPI, lifespan Playwright e registro de rotas
|-- routes/                   # Endpoints HTTP e mapeamento de respostas
|-- services/                 # Orquestracao de pipeline, etapas, Playwright pool e classificador
|-- parsers/                  # Parsers por estrategia e por dominio
|-- utils/                    # HTTP (curl_cffi), cache, robots, DNS, retries, headers
|-- schemas/                  # Schemas locais de apoio
└──  tests/                   # Suite de testes
```

---

## Endpoints e Fluxos HTTP
As rotas publicas são registradas em [`main.py`](main.py), com foco em um endpoint de parsing e um endpoint de saude. O fluxo principal da API combina validação de URL, revalidação condicional por cache e execução do pipeline de scraping.

### Fluxos HTTP mais relevantes
- Parse sincrono: `POST /scraper/parse` recebe `ParserRequest`, normaliza a URL e valida compatibilidade minima antes do pipeline.
- Revalidação condicional: se o cliente enviar `If-None-Match` e/ou `If-Modified-Since`, o endpoint pode responder `304` sem corpo.
- Bypass de cache por metadata: `metadata.force_refresh=true` ignora cache condicional e forca nova coleta.
- Mapeamento de erros operacionais: `invalid_url`, `blocked_host`, `unsupported_by_robots`, `too_many_redirects`, `no_result` e `pipeline_timeout` são traduzidos para status HTTP previsiveis.
- Contrato de resposta consistente: em `200`, retorna `ParserResponse` e inclui `ETag`, `Last-Modified`, `Cache-Control` e `X-MarketScraper-Cache-Status`.

## Dominios e Componentes Chave

### API HTTP e Contratos
- [`main.py`](main.py) instancia o FastAPI e registra `routes_health` e `routes_scraper`.
- [`routes/routes_scraper.py`](routes/routes_scraper.py) executa o fluxo HTTP completo: validação, cache condicional, pipeline e resposta.
- [`routes/response_helpers.py`](routes/response_helpers.py) padroniza respostas de erro/sucesso e converte problemas de pipeline para `error_code` estável.
- [`shared/schemas/shared_schemas_scraper.py`](../shared/schemas/shared_schemas_scraper.py) define os contratos compartilhados (`ParserRequest`, `ParserResponse`, `ErrorResponse`).

### Orquestracao de Pipeline
- [`services/pipeline_factory.py`](services/pipeline_factory.py) monta `PipelineContext`, cria pipeline padrao e oferece `run_pipeline`.
- [`services/synergic_pipeline.py`](services/synergic_pipeline.py) executa as etapas em sequencia com timeout por etapa e timeout global.
- [`services/pipeline_steps.py`](services/pipeline_steps.py) define as etapas concretas (`FetchHTMLStep`, `JsonLdParserStep`, `HtmlMetadataParserStep`, `DomainSpecificParserStep`, `GenericFallbackParserStep`).
- [`services/parser_runner.py`](services/parser_runner.py) centraliza execução/validação de parser e sincronização dos dados no contexto.

### Parsers e Inferencia
- [`parsers/domain_parsers.py`](parsers/domain_parsers.py) mapeia parsers por sufixo de domínio (`mercadolivre`, `amazon`, `magalu`).
- [`parsers/extruct.py`](parsers/extruct.py), [`parsers/beautifulsoup.py`](parsers/beautifulsoup.py) e [`parsers/html_static.py`](parsers/html_static.py) cobrem estratégias de parsing estrutural e fallback generico.
- [`services/availability_inference.py`](services/availability_inference.py) infere disponibilidade e `last_status` em cenarios HTTP sem payload de produto.

### Infraestrutura de Scraping e Cache
- [`utils/http_download.py`](utils/http_download.py) implementa `CurlffiHTTPClient` com TLS impersonation Chrome124 via `curl_cffi`. Mapeia erros para `httpx.*` equivalentes para a tentativa HTTP primária executada pelo `FetchDecisionGate`.
- [`services/response_classifier.py`](services/response_classifier.py) classifica cada resposta em `SUCCESS`, `SCALE` ou `REJECT` com base em status HTTP, tamanho do HTML e padrões anti-bot.
- [`services/playwright_pool.py`](services/playwright_pool.py) gerencia pool singleton de Playwright com semáforo de concorrência, stealth injection e bloqueio de recursos pesados.
- [`infra/adaptive_rate_limiter.py`](infra/adaptive_rate_limiter.py) rastreia taxa de sucesso por hostname no Redis e sugere a estratégia de aquisição mais barata possível. Ativa cooldown automático em cenários de 429 recorrente.
- [`utils/http_retry.py`](utils/http_retry.py) aplica politicas de retry com backoff para alvos HTTP.
- [`utils/http_utils.py`](utils/http_utils.py) resolve DNS com cache e bloqueia hosts/IPs não publicos (protecao SSRF).
- [`utils/robots.py`](utils/robots.py) valida `robots.txt` antes da coleta via Redis operacional (db 2); fallback atual e restritivo (bloqueia quando não consegue validar o parser).
- Rate limiting adaptativo usa chaves com prefixo `rate:ml:{host}` no Redis operacional (db 2), isolado do broker Celery (db 0) e do result backend (db 1).
- [`utils/cache.py`](utils/cache.py), [`utils/singleflight.py`](utils/singleflight.py) e [`utils/conditional_payload.py`](utils/conditional_payload.py) suportam cache em memória, coalescing e revalidação condicional HTTP.

#### Endpoints - Market Scraper
| Metodo | Rota | Contrato principal | Codigos mais comuns |
|--------|------|--------------------|---------------------|
| `POST` | `/scraper/parse` | `ParserRequest` -> `ParserResponse` | `200`, `304`, `400`, `403`, `422`, `504` |
| `GET` | `/health/ping` | sem payload -> `{ "status": "ok" }` | `200` |

### Integracao com market_alert
- O cliente oficial vive em [`../shared/clients/scraper/scraper_client.py`](../shared/clients/scraper/scraper_client.py).
- O cliente encapsula retries, rate limit por host, circuit breaker, cabeçalhos condicionais e suporte opcional a header de autenticação de serviço (`SCRAPER_SERVICE_AUTH_*`).

---

## Arquitetura de Aquisição HTML

O serviço continua usando aquisição em cascata, mas o ponto único de decisão agora é o [`FetchDecisionGate`](services/fetch_decision_gate.py). A etapa de pipeline `FetchHTMLStep` só faz três coisas: validar `robots.txt`, reutilizar cache quando permitido e delegar a aquisição ao gate.

### Responsabilidades por componente

| Componente | Responsabilidade |
|-----------|------------------|
| `FetchHTMLStep` | Adaptar `PipelineContext` para `FetchResult`, preencher `context.html` e gravar telemetria em `context.data` |
| `FetchDecisionGate` | Orquestrar rate limiter, tentativa HTTP, classificação da resposta, fallback para browser e mapeamento final do resultado |
| `ResponseClassifier` | Decidir `SUCCESS`, `SCALE` ou `REJECT` sem I/O, com base em status HTTP, HTML e exceção |
| `AdaptiveRateLimiter` | Definir se o host pode prosseguir e quando vale insistir na tentativa HTTP antes do browser |
| `PlaywrightPool` | Executar o fallback de browser com Chromium, sem expor lifecycle do browser ao restante do pipeline |

### Arquitetura do `FetchDecisionGate`

```
POST /scraper/parse
        │
        ▼
FetchHTMLStep
        │
        ├── robots.is_allowed(url) = false → 403 unsupported_by_robots
        ├── cache.get(url) = hit          → 200 html_from_cache
        │
        ▼
FetchDecisionGate.fetch_with_fallback(...)
        │
        ├── adaptive_rate_limiter.should_allow(host) = false
        │   └── REJECT(rate_limiter_cooldown)
        │
        ├── download_html() via curl_cffi + singleflight
        │
        ├── ResponseClassifier.classify(status, html, error)
        │   ├── SUCCESS → HTML aceito via HTTP
        │   ├── REJECT  → erro final ou indisponibilidade inferida
        │   └── SCALE   → playwright_pool.fetch_html()
        │               ├── sucesso → HTML aceito via browser
        │               └── erro    → rejeição degradada ou challenge persistente
        │
        └── FetchResult(status, html, error_code, telemetry)
```

### Fluxo de fallback HTTP → Browser

1. A primeira tentativa sempre privilegia `curl_cffi`, porque é mais barata, mais rápida e já resolve a maioria dos casos.
2. O `ResponseClassifier` olha para o resultado bruto dessa tentativa e decide se o HTML é utilizável, se deve ser descartado imediatamente ou se vale escalar.
3. Só há fallback para `Playwright` quando o retorno sugere bloqueio, HTML vazio, erro transitório ou necessidade de renderização.
4. O browser não roda em paralelo com a tentativa HTTP; ele é acionado somente quando a decisão `SCALE` torna isso necessário.
5. O resultado devolvido ao pipeline já sai consolidado em `FetchResult`, sem lógica anti-bot duplicada em outras etapas.

### Classificador de Resposta (`ResponseClassifier`)

Centraliza as regras de escalonamento sem lógica espalhada nas etapas:

| Condição | Ação | Destino |
|----------|------|---------|
| 200 + HTML válido (≥ 1 KB, sem anti-bot) | `SUCCESS` | seguir para parsing |
| 200 + HTML vazio ou anti-bot detectado | `SCALE` | fallback para browser |
| 429 | `SCALE` | fallback para browser |
| 403 / 405 / 5xx | `SCALE` | fallback para browser |
| 404 / 410 | `REJECT` | encerrar |
| Timeout / ConnectionError | `SCALE` | fallback para browser |

Padrões anti-bot detectados: `suspicious-traffic-frontend` (Mercado Livre), `challenges.cloudflare.com`, `__cf_chl`, `__cf_bm`, `recaptcha/api.js`, `_pxcaptcha`.

### Anti-bot: detecção vs bloqueio

- **Detecção** significa que o classificador ou o gate encontraram evidência de challenge no HTML (`anti_bot_detected=true`, `anti_bot_pattern=...`). Isso não implica falha final por si só.
- **Bloqueio** significa que, depois da decisão do gate, o endpoint realmente precisou devolver erro para o cliente (`429`, `503` ou `504`) porque não havia HTML utilizável.
- Um `200` com HTML de challenge conta como detecção e normalmente leva a `SCALE`, não a erro imediato.
- Se o browser consegue renderizar a página e o challenge desaparece, o gate marca `anti_bot_bypassed=true` e o pipeline segue normalmente.
- Se o browser também falha, o problema vira bloqueio efetivo e é mapeado por `response_helpers.py` para um `error_code` estável.

### Rate Limiter Adaptativo (`AdaptiveRateLimiter`)

Rastreia taxa de sucesso por hostname com histórico em Redis (db 2) e ativa cooldown automático quando a taxa cai abaixo dos limiares.

**Limiares de decisão:**

| Taxa de sucesso | Estratégia sugerida | Ação de cooldown |
|-----------------|---------------------|------------------|
| ≥ 90 % | insistir na tentativa HTTP | — |
| 50 – 89 % | aceitar escalonamento para browser quando necessário | — |
| 20 – 49 % + 429 recorrente | aceitar escalonamento para browser | Cooldown 300 s |
| < 20 % | rejeitar temporariamente | Cooldown 3600 s |

**Chaves Redis** (prefixo `rate:ml:{hostname}`, TTL 1h, db 2):

| Chave | Tipo | Conteúdo |
|-------|------|----------|
| `rate:ml:{host}:success_count` | INCR | Requisições bem-sucedidas |
| `rate:ml:{host}:failure_count` | INCR | Requisições com erro |
| `rate:ml:{host}:cooldown_until` | SET | Timestamp Unix (float) de fim do cooldown |
| `rate:ml:{host}:last_layer` | SET | Estratégia usada na última requisição (`1` HTTP, `3` browser; nome histórico preservado na chave) |
| `rate:ml:{host}:last_error_code` | SET | Último código de erro (`429`, `timeout`, …) |

Quando Redis está indisponível, o limiter usa fallback in-memory (não persistente) — degradação segura sem interromper o pipeline.

### Playwright Pool

- **Pool singleton** (`playwright_pool`) inicializado no lifespan do FastAPI.
- **Semáforo** limita a `PLAYWRIGHT_MAX_CONCURRENT` contexts simultâneos (padrão: 5 → máx ~30 req/min).
- **Stealth**: injeta script JS que oculta `navigator.webdriver`, adiciona plugins Chrome e define `navigator.languages = ['pt-BR', 'pt', 'en-US', 'en']`.
- **Bloqueio de recursos**: imagens, CSS, fontes e mídias são abortados (~40 % menos RAM por contexto).
- **Memória**: ~200 MB por context Playwright. Use `--shm-size=2g` no Docker ou configure `PLAYWRIGHT_DISABLE_DEV_SHM=1`.

---

## Pipeline de Parsing
O pipeline sequencial e registrado em [`services/pipeline_steps.py`](services/pipeline_steps.py) e executado por [`services/synergic_pipeline.py`](services/synergic_pipeline.py). A execução para no primeiro `StepResult.success` com payload valido.

1. **FetchHTMLStep**: etapa oficial de aquisição de HTML. Ela delega ao `FetchDecisionGate`, que concentra rate limiter, tentativa HTTP, classificação e fallback para browser.
2. **JsonLdParserStep**: tenta extrair dados estruturados (`application/ld+json`) com `extruct`.
3. **HtmlMetadataParserStep**: tenta extrair nome/preco/metadados com BeautifulSoup.
4. **DomainSpecificParserStep**: aplica parser dedicado quando o dominio bate com mapeamento conhecido.
5. **GenericFallbackParserStep**: ultima tentativa com heuristicas genericas.

Tempo maximo por etapa: `SCRAPER_STEP_TIMEOUT_SECONDS`. Tempo total do pipeline: `SCRAPER_PIPELINE_TIMEOUT_SECONDS`.

### Mapa do Pipeline de Parsing
| Ordem | Etapa | Objetivo | Possivel saida |
|-------|-------|----------|----------------|
| `1` | `FetchHTMLStep` | Obter HTML ou inferir indisponibilidade, delegando a decisão de aquisição ao `FetchDecisionGate` | `success`, `error` |
| `2` | `JsonLdParserStep` | Extrair dados estruturados com maior confiabilidade | `success` com payload ou `empty` |
| `3` | `HtmlMetadataParserStep` | Ler metadados e estrutura basica da pagina | `success` com payload ou `empty` |
| `4` | `DomainSpecificParserStep` | Aplicar regras dedicadas por dominio quando disponiveis | `success` com payload ou `empty` |
| `5` | `GenericFallbackParserStep` | Aplicar heuristicas genericas como ultimo fallback | `success` com payload ou `empty` |

### Telemetria no contrato HTTP

**Headers garantidos pela rota `POST /scraper/parse`:**

| Header | Quando aparece | Significado |
|--------|----------------|-------------|
| `X-MarketScraper-Contract-Version` | Todas as respostas do endpoint | Versão major do contrato HTTP compartilhado |
| `X-MarketScraper-Cache-Status` | Respostas emitidas pela rota após lookup condicional | Estado do cache HTTP: `hit`, `miss`, `revalidated` ou `bypass` |
| `ETag`, `Last-Modified`, `Cache-Control` | Quando existe metadata persistida para a resposta | Revalidação condicional e reaproveitamento pelo cliente |

**Campos do corpo relevantes para rastreabilidade:**

| Campo | Local | Observação |
|------|-------|------------|
| `availability` | topo do `ParserResponse` | Disponibilidade consolidada do anúncio |
| `last_status` | topo do `ParserResponse` | Último estado conhecido ou inferido |
| `payload` | `ParserResponse.payload` | Extras do parser preservados para auditoria sem quebrar o contrato, incluindo `acquisition` quando houver telemetria de coleta |

**Telemetria interna de aquisição:**

- `http_status`
- `layer_used`
- `fallback_taken`
- `anti_bot_detected`
- `anti_bot_pattern`
- `anti_bot_bypassed`
- `classification_reason`

Esses campos são gravados em `PipelineContext.data` e em logs estruturados para auditoria operacional. O contrato HTTP atual não os expõe como headers dedicados nem os injeta automaticamente no `ParserResponse.payload`; qualquer futura exposição deve ser tratada como adição explícita e compatível de contrato.

---

## Fluxo de Trabalho

### Fluxo sincrono de parse (request -> response)
1. Cliente envia `POST /scraper/parse` com `ParserRequest`.
2. A rota normaliza URL e aplica validacoes de compatibilidade (`invalid_url`, `blocked_host`, etc.).
3. Se não houver `force_refresh`, o endpoint tenta usar metadados em cache para responder `304`.
4. Sem `304`, o endpoint executa `run_pipeline(...)`.
5. O pipeline percorre as etapas em ordem fixa ate encontrar payload valido.
6. Em `success`, a rota monta `ParserResponse`, registra logs e persiste metadados condicionais (`ETag`/`Last-Modified`).
7. Em `no_result` ou erros mapeados, retorna JSON de erro padronizado com `error_code` e `trace_id`.

### Fluxo de cache condicional HTTP
1. Em resposta `200`, o endpoint gera hash estável do payload e armazena metadados condicionais por URL.
2. O cliente reaproveita `ETag` e `Last-Modified` em chamadas futuras.
3. Se a condicao casar (`If-None-Match` ou `If-Modified-Since`), a resposta e `304 Not Modified`.
4. Se houver `metadata.force_refresh=true`, a rota ignora cache condicional e executa coleta completa.
5. O header `X-MarketScraper-Cache-Status` indica decisão (`hit`, `miss`, `revalidated`, `bypass`).

---

## Fluxos de Negocio End-to-End

### 1. Parse com snapshot novo (`200`)
1. `market_alert` chama `POST /scraper/parse` com URL e contexto (`product_type`, `user_id`, `metadata`).
2. O scraper valida URL/host publico e passa pelo pipeline.
3. Uma etapa retorna payload valido (`name`, `current_price`, `availability`, etc.).
4. A rota converte preco para decimal, normaliza resposta e devolve `200`.
5. Metadados condicionais são persistidos para reuso nas proximas coletas.

### 2. Revalidação condicional (`304 Not Modified`)
1. Cliente envia `If-None-Match`/`If-Modified-Since` com valores da coleta anterior.
2. O scraper consulta metadados em cache da URL.
3. Se não houver mudança, retorna `304` sem corpo.
4. `market_alert` interpreta como `not_modified` e evita persistencia redundante.

### 3. URL invalida ou bloqueada (`400`/`403`/`422`)
1. URL malformada, protocolo invalido ou host não publico retorna erro controlado.
2. Bloqueio por `robots.txt` retorna `403` com `error_code=unsupported_by_robots`.
3. Loop de redirecionamento ou URL invalida em download retorna `422`.
4. Em todos os casos, a resposta inclui `trace_id` para correlacao com logs.

### 4. Pipeline sem dados confiaveis (`422` com `no_result`)
1. O pipeline executa todas as etapas e nenhuma retorna payload valido.
2. A rota retorna erro controlado `no_result`.
3. O cliente chamador pode aplicar politica de retry/backoff sem quebrar contrato HTTP.

---

## Configuração
As configurações combinam base compartilhada em [`../shared/core/config_base.py`](../shared/core/config_base.py) com overrides específicos em [`core/config_scraper.py`](core/config_scraper.py).

### Ordem de carregamento de ambiente
1. `ConfigBase` carrega `.env.common` com `override=False` (preenche apenas variaveis ausentes).
2. Se `SERVICE_NAME` estiver definido, carrega `.env.<SERVICE_NAME>` com `override=True`.
3. Caso contrario, usa `ENV_FILE` (ou `.env`) e carrega com `override=True`.
4. Depois disso, `Settings` do scraper aplica defaults de codigo para chaves ainda ausentes.
5. Nos compose ativos (`docker-compose.dev.yml` e `docker-compose.hml.yml`), `market_scraper` sobe com `env_file: ./backend/market_scraper/.env.market_scraper` e `ENV_FILE=.env.market_scraper`, mantendo o arquivo local do servico como fonte principal de override.
6. Em teste (`PYTEST_RUNNING=1`), o bootstrap ignora completamente `.env.common`, `.env`, `.env.<service>` e `ENV_FILE`; a suite usa apenas defaults locais em `tests/conftest.py` e overrides explicitos do teste.

### Categorias de variaveis
| Categoria | Variaveis relevantes |
|-----------|----------------------|
| Pipeline e cache | `SCRAPER_CACHE_TTL_SECONDS`, `SCRAPER_CACHE_MAX_ENTRIES`, `SCRAPER_STEP_TIMEOUT_SECONDS`, `SCRAPER_PIPELINE_TIMEOUT_SECONDS`, `SCRAPER_SINGLEFLIGHT_*` |
| HTTP e rede | `SCRAPER_HTTP_TIMEOUT_*`, `SCRAPER_HTTP_RETRIES`, `SCRAPER_HTTP_RETRY_BACKOFF_BASE`, `SCRAPER_HTTP_MAX_*`, `SCRAPER_DNS_TIMEOUT`, `SCRAPER_DNS_CACHE_TTL` |
| Headers e identidade | `SCRAPER_DEFAULT_USER_AGENT`, `SCRAPER_USER_AGENT_POOL`, `SCRAPER_HEADERS_*` |
| Parsing e qualidade de dado | `SCRAPER_PRICE_TOLERANCE`, `SCRAPER_HTTP_DOMAIN_TIMEOUTS` |
| **Playwright** | `PLAYWRIGHT_MAX_CONCURRENT` (padrão: `5`) — máximo de contexts simultâneos; `PLAYWRIGHT_DISABLE_DEV_SHM` (qualquer valor não-vazio) — usa `--disable-dev-shm-usage` em vez de `/dev/shm` |
| Base compartilhada | `REDIS_HOST`, `REDIS_PORT`, `REDIS_PASSWORD`, `REDIS_OPERATIONAL_DB` (db 2 — locks, rate limiting e cache de robots), `LOG_LEVEL`, `LOG_FORMAT`, `ROBOTS_CACHE_*`, `CIRCUIT_*` |

Exemplo minimo de `.env.market_scraper`:
```env
SCRAPER_CACHE_TTL_SECONDS=3600
SCRAPER_CACHE_MAX_ENTRIES=5000
SCRAPER_SINGLEFLIGHT_LOCK_TTL=15.0
SCRAPER_SINGLEFLIGHT_MAX_ENTRIES=2000

SCRAPER_STEP_TIMEOUT_SECONDS=8.0
SCRAPER_PIPELINE_TIMEOUT_SECONDS=20.0

SCRAPER_HTTP_TIMEOUT_CONNECT=3.0
SCRAPER_HTTP_TIMEOUT_READ=3.0
SCRAPER_HTTP_TIMEOUT_WRITE=3.0
SCRAPER_HTTP_TIMEOUT_POOL=3.0

SCRAPER_HTTP_RETRIES=2
SCRAPER_HTTP_RETRY_BACKOFF_BASE=0.5
SCRAPER_HTTP_MAX_REDIRECTS=3
SCRAPER_HTTP_MAX_CONTENT_LENGTH=2000000

SCRAPER_DEFAULT_USER_AGENT=Mozilla/5.0
SCRAPER_PRICE_TOLERANCE=0.0
```

---

## Testes
O `market_scraper` possui suite local isolada em [`tests/`](tests) e usa somente [`../pytest.ini`](../pytest.ini) como configuracao central do `pytest`. O bootstrap de teste nao usa `.env.test`: [`tests/conftest.py`](tests/conftest.py) define defaults locais em Python, reseta estado global do modulo e ativa o modo teste com `PYTEST_RUNNING=1`.

### Estrutura da suite
- [`tests/unit`](tests/unit): regras isoladas, sem I/O real, com mocks e fakes para cache, rede, parsers e rotas.
- [`tests/integration`](tests/integration): fluxos ponta a ponta internos do modulo usando `TestClient`, pipeline real e HTML de fixture deterministico.
- [`tests/stress`](tests/stress): testes tecnicos de timeout e volume controlado sem acesso externo real.
- [`tests/fixtures`](tests/fixtures): HTMLs fixos usados para manter cenarios repetiveis e sem flakiness.

### Comandos oficiais
Executar a partir da raiz do repositorio `market_suite`:

```powershell
.\.venv\Scripts\python.exe -m pytest -c backend/pytest.ini backend/market_scraper/tests/unit -q
.\.venv\Scripts\python.exe -m pytest -c backend/pytest.ini backend/market_scraper/tests/integration -q
.\.venv\Scripts\python.exe -m pytest -c backend/pytest.ini backend/market_scraper/tests/stress -q
.\.venv\Scripts\python.exe -m pytest -c backend/pytest.ini backend/market_scraper/tests -m unit -q
.\.venv\Scripts\python.exe -m pytest -c backend/pytest.ini backend/market_scraper/tests --cov=market_scraper --cov-report=term -q
```

Comandos de apoio operacional:

```powershell
.\.venv\Scripts\python.exe -m pytest -c backend/pytest.ini backend/market_scraper/tests/stress -q
.\.venv\Scripts\python.exe -m pytest -c backend/pytest.ini backend/market_scraper/tests --collect-only -q
```

### Politica de manutencao da suite
- Toda mudanca em contrato HTTP, mapeamento de `error_code`, ordem do pipeline, timeouts ou cache condicional deve atualizar ao menos uma suite relevante (`unit`, `integration` ou `stress`).
- Testes `unit` nao devem fazer rede, DNS, Redis ou acesso externo real; usar `monkeypatch`, fakes e fixtures locais.
- Testes `integration` devem exercitar somente fluxos internos do modulo com infraestrutura controlada e HTML fixo em `tests/fixtures`.
- Testes `stress` devem permanecer pequenos, deterministas e limitados a timeout, concorrencia controlada e estabilidade de resposta.
- Estado global do modulo (`cache`, `singleflight` e settings carregados) deve continuar sendo resetado por teste via [`tests/conftest.py`](tests/conftest.py).
- A configuracao canônica do `pytest` segue centralizada em [`../pytest.ini`](../pytest.ini), sem `pytest.ini` local no modulo.
- Nenhum teste deve depender de `.env.market_scraper.test`, `ENV_FILE` ou leitura implícita de `.env` operacional.
- Novos parsers ou novos erros de fluxo devem vir acompanhados de cobertura minima em `unit` e `integration` antes de serem considerados prontos.

### Cobertura atual da suite
- `unit`: configuracao, contratos do pipeline, etapas com mocks de I/O, helpers de resposta, utilitarios criticos e rota. Inclui cobertura dedicada para `CurlffiHTTPClient`, `ResponseClassifier`, `PlaywrightPool`, `AdaptiveRateLimiter` e `FetchHTMLStep`.
- `integration`: `health`, sucesso do parse, `304`, `force_refresh`, erros de fluxo, fallback por etapas e compatibilidade com schemas compartilhados.
- `stress`: timeout por etapa, timeout global e volume concorrente controlado com resposta estavel.

---

## Seguranca e Observabilidade
- **Seguranca:**
  - Validação de URL e host publico em `shared/utils/url_validation.py` + `utils/http_utils.py` para reduzir risco de SSRF.
  - Bloqueio por `robots.txt` antes do download (`utils/robots.py`), com fallback restritivo quando o parser não pode ser validado.
  - Limites defensivos em download (`SCRAPER_HTTP_MAX_REDIRECTS`, `SCRAPER_HTTP_MAX_CONTENT_LENGTH`) e retries com backoff controlado.
  - TLS impersonation via `curl_cffi` (Chrome124) — não utiliza proxy; sem credenciais externas necessárias.
  - Erros de dominio são retornados com `error_code` estável para tratamento previsivel no cliente.

- **Observabilidade:**
  - Logs estruturados por `trace_id` em rota e pipeline (`routes_scraper`, `scraper_pipeline`), incluindo etapa, resultado e duracao.
  - Telemetria de aquisição (`layer_used`, `classification_reason`, `fallback_taken`, `anti_bot_*`) fica centralizada em `context.data` e nos logs estruturados do gate.
  - `X-MarketScraper-Cache-Status` facilita diagnostico de decisoes de cache condicional.
  - Health check simples em `/health/ping` para probes de orquestracao.

---

## Fronteiras de Domínio

### Matriz de Responsabilidade

| Módulo | Pode depender de | NÃO pode depender de |
|--------|-----------------|----------------------|
| `market_scraper` | `shared` (contratos neutros) | `market_alert`; `market_orchestrator` |
| `market_alert` | `market_scraper` via HTTP apenas | — |
| `shared` | bibliotecas externas | `market_scraper`; `market_alert`; `market_orchestrator` |

### Regras Obrigatórias

- **`market_scraper` NÃO importa `market_alert`** — é um microserviço independente consumido via HTTP.
- **`market_scraper` NÃO importa `market_orchestrator`** — não tem conhecimento do ciclo de orquestração.
- **Contratos de entrada/saída** são definidos exclusivamente em `shared/schemas/shared_schemas_scraper.py` (`ParserRequest`, `ParserResponse`, `ErrorResponse`).
- **Configuração interna** (`core/`) é isolada; sem uso de `shared.core.config_base` que carregue segredos de outros serviços.

---

> Nota final: mantenha este README do `market_scraper` atualizado sempre que houver mudança de endpoint, contrato HTTP, ordem do pipeline, regras de parser ou configuracao operacional do servico.
