# Market Alert
API FastAPI responsável por autenticação, gestão e monitoramento, comparação de preços e disparo de notificações. Opera com PostgreSQL, Redis, Celery (worker + beat) e integra o `market_scraper` para coleta de dados.

## Relações e Referências
- Visão geral da suíte e topologia: [`../README.md`](../README.md)
- Detalhes do serviço de scraping: [`../market_scraper/README.md`](../market_scraper/README.md)
- Guia operacional para agentes: [`../AGENTS.md`](../AGENTS.md)

## Principais Responsabilidades
- **Expor rotas REST** para gerenciamento de usuários, autenticação, produtos monitorados e concorrentes, comparações e notificações.
- **Agendar tarefas Celery** (`scraping`, `monitor`, `metrics`) para coleta de dados, rechecagens, envio de alertas e coleta de métricas.
- **Persistir dados** em PostgreSQL utilizando SQLAlchemy (módulos `models/` e `crud/`).
- **Registrar métricas e logs estruturados** para Prometheus e Loki.
- **Integrar com o `market_scraper`** usando `ScraperClient` (`services/scraper_client.py`).
- **Regras Comparação** deve ser realizado automaticamente, sem haver possibilidade de ser realizada manualmente, ou forçar comparação, seguir um padrão para quando houver comparações entre os produtos.
- **Simplificar alertas** priorizando apenas mudanças de preço e disponibilidade, sem thresholds dinâmicos ou idempotência distribuída (regra de alerta padronizada pelo sistema, sem possibilidade de criação de regras, alterações, etc).

## Estrutura do Diretório
```text
market_alert/
├── auth/                #Fluxos de autenticação, JWT e rotas de login/refresh/reset
├── core/                #Configuração do serviço, inicialização do Celery e carregamento de env
├── crud/                #Operações de banco de dados (SQLAlcemy Session)
├── models/              #Modelos ORM (SQLAlchemy)
├── routes/              #Rotas FastAPI (usuários, monitoramentos, notificações, etc.)
├── schemas/             #Modelos Pydantic expostos pela API
├── services/            #Regras de negócio (scraper client, comparações, notificações)
├── tasks/               #Conjunto de tasks Celery (scraping, monitoramento, métricas, alertas)
├── notifications/       #Templates e canais de envio de notificação
├── templates/           #Recursos HTML/Texto para e-mails e mensagens
└── utils/               #Auxiliares (cache, rate limiting, serialização, etc.)
```

## Endpoints e Fluxos Relevantes
| Método | Rota / Fluxo | Descrição |
|--------|--------------|-----------|
| `POST` | `/auth` | Autenticação via formulário e emissão de JWT. |
| `POST` | `/auth/refresh` | Renova token de acesso ativo. |
| `GET` | `/monitored` | Lista monitorados paginados usando envelope `{ items, meta }` com filtros `page`, `per_page`, `query` e `status`. |
| `GET` | `/monitored/{id}` | Retorna detalhes do monitorado com `owner_id`, `thumbnail`, `current_price` (`Decimal` serializado) e `last_scraped_at`. |
| `GET` | `/monitored/featured` | Retorna até 3 monitorados em destaque respeitando `is_featured` e ordenação configurada. |
| `POST` | `/monitored/scrape` | Valida duplicidade por usuário + URL, cria recurso mínimo (`id`, `url`, `created_at`) e agenda coleta na fila `scraping`. |
| `POST` | `/monitored` | Cria produto monitorado associado ao usuário autenticado (fluxo alternativo ao scrape imediato). |
| `GET` | `/comparisons/{monitored_id}` | Lista comparações paginadas (`items` + `meta`) para o monitorado informado. |
| `GET` | `/comparisons/{monitored_id}/summary` | Consolida métricas de comparação; `Decimal` enviado como número apenas no resumo (encoder existente). |
| `GET` | `/competitors` | Lista concorrentes vinculados a um monitorado com paginação e campos `thumbnail`/`last_scraped_at`. |
| `POST` | `/competitors/scrape` | Valida duplicidade por `monitored_id` + URL, cria recurso mínimo e agenda coleta na fila `scraping`. |
| `GET` | `/notifications` | Lista histórico e status de notificações geradas. |
| `GET` | `/metrics` | Exibe métricas Prometheus da API. |
| `Celery` | `tasks.monitor_tasks.collect_product_task` | Consome fila `scraping` para coletar dados do monitorado (payload mínimo e idempotente). |
| `Celery` | `tasks.monitor_tasks.collect_competitor_task` | Coleta concorrentes vinculados, recalcula comparações e grava `PriceHistory`. |
| `Celery` | `tasks.compare_prices_tasks.compare_prices_task` | Recalcula comparação e `competitiveness_status` após coletas. |
| `Celery` | `tasks.alert_tasks.dispatch_price_alert_task` | Enfileira alertas quando regras de preço são acionadas. |

### Integração com os Serviços
- **`market_scraper`**: consumido por `scraper/scraper_client.ScraperClient`, que envia `ParserRequest` valida `ParserResponse` do pacote e trata `304 Not Modified` retornando `None` quando nada mudou.
- **`shared/`**: reutiliza abstrações de configuração, métricas (`shared/metrics/metrics_api.py`), segurança e utilidades comuns.
- **Infraestrutura comum**: compartilha Redis (fila Celery/cache) e Postgres definidos no `docker-compose.yml`, além do `.env.common` para logs e tracing.
- **Codificação numérica**: valores monetários são serializados como string (`Decimal` → `"1099.90"`) em quase todos os contratos, exceto no resumo de comparação que mantém encoder numérico para compatibilidade.
- **Execução das comparações**: as comparações são executadas automaticamente pelas tasks de monitoramento e comparação; não há endpoint para disparo manual.

> O canal WebSocket de notificações permanece desativado temporariamente; utilize `/notifications/logs` e polling no frontend para acompanhar alertas.

## Celery
- **Arquivo principal:** `core/celery_app.py`.
- **Filas padrão:** `celery`, `scraping`, `monitor` (configuráveis via `.env.market_alert`).
- **Tasks de destaque:**
  - `tasks.monitor_tasks.collect_product_task`
  - `tasks.monitor_tasks.collect_competitor_task`
  - `tasks.compare_prices_tasks.compare_prices_task`
  - `tasks.alert_tasks.dispatch_price_alert_task`
  - `tasks.metrics_tasks.collect_celery_metrics`, `cleanup_cache`
  - `tasks.monitor_tasks.recheck_monitored_products`, `recheck_competitor_products`
- **Beat com métricas:** `beat_with_metrics.py` executa agendamentos e expõe `/metrics` em porta dedicada (`8001`).

## Configuração
Variáveis padrão residem em [`core/config_alert.py`](core/config_alert.py) e podem ser sobrescritas via `market_alert/.env.market_alert`.

| Categoria | Variáveis relevantes |
|-----------|----------------------|
| Banco de dados | `DATABASE_URL`, `SQLALCHEMY_POOL_SIZE`, `SQLALCHEMY_MAX_OVERFLOW`, `DB_ECHO` |
| Celery | `CELERY_BROKER_URL`, `CELERY_RESULT_BACKEND`, `CELERY_TASK_ROUTES`, `CELERY_TIMEZONE`, `CELERY_BEAT_SCHEDULE_FILE` |
| Scraper | `SCRAPER_BASE_URL`, `SCRAPER_TIMEOUT_SECONDS`, `SCRAPER_SERVICE_AUTH_HEADER`, `SCRAPER_SERVICE_AUTH_TOKEN` |
| Notificações | `NOTIFICATION_FROM_EMAIL`, `NOTIFICATION_WEBHOOK_URL`, `NOTIFICATION_COOLDOWN_SECONDS`, `NOTIFICATION_CHANNELS` |
| Observabilidade | `SERVICE_NAME`, `OTEL_EXPORTER_OTLP_ENDPOINT`, `METRICS_PORT`, `LOG_LEVEL` |

### Padrões de contratos
- **Paginação**: todas as rotas de listagem utilizam envelope `{ items: [], meta: { total, page, per_page } }` com paginação base 1.
- **Campos monetários**: valores `Decimal` são serializados como string (`"1099.90"`) por padrão. O resumo de comparação mantém encoder que envia números (`1099.9`) e deve ser tratado pelo frontend.
- **Criar via scraping**: endpoints `/monitored/scrape` e `/competitors/scrape` retornam 202 com representação mínima do recurso (`id`, `url`, `created_at`) e enfileiram coleta na fila `scraping`.
- **Destaques**: `/monitored/featured` devolve até 3 monitorados com `is_featured=true`, ordenados pelo critério definido em `routes_monitored`.

## Principais Componentes do Serviço
- `main.py` – instancia a aplicação FastAPI, middlewares, limiter e rotas.
- `core/config_alert.py` – carrega variáveis de ambiente e aplica defaults.
- `core/celery_app.py` – configura worker, beat e registradores de métricas.
- `services/scraper_client.py` – encapsula chamadas HTTP ao `market_scraper` com autenticação.
- `services/comparison_service.py` – orquestra cálculos de comparação e dispara regras.
- `tasks/monitor_tasks.py` – concentra tasks de coleta de monitorados e concorrentes.
- `tasks/alert_tasks.py` – envia notificações e aplica cooldowns.
- `tasks/metrics_tasks.py` – publica métricas periódicas da fila e recursos.
- `tasks/compare_prices_tasks.py` – recalcula históricos de comparação e atualiza `competitiveness_status` após scraping.

Exemplo mínimo de `.env.market_alert`:
```env
DATABASE_URL=postgresql+asyncpg://market:market@db:5432/market

CELERY_BROKER_URL=redis://redis:6379/0
CELERY_RESULT_BACKEND=redis://redis:6379/1
CELERY_TASK_ROUTES={"tasks.monitor_tasks.*": {"queue": "scraping"}}

SCRAPER_BASE_URL=http://market_scraper:8010
SCRAPER_TIMEOUT_SECONDS=15
SCRAPER_SERVICE_AUTH_TOKEN=token-exemplo

NOTIFICATION_FROM_EMAIL=alerts@empresa.dev
SERVICE_NAME=market-alert
```

## Segurança e Observabilidade
- **Segurança:**
  - JWT curto com refresh token
  - Filtragem de payloads e segregação de permissões por usuário
  - Segredos permanecem em arquivos `.env` ignorados pelo Git.

- **Observabilidade:**
  - Métricas expostas em `/metrics`
  - Logs estruturados via `structlog`
   - Métricas Celery disponíveis em `beat_with_metrics.py` na porta configurada, incluindo contadores de scraping e latência (`market_alert_monitoring_tasks_total`, `market_alert_scrape_latency_seconds`).
  - Tracing opcional via OTEL (`OTEL_EXPORTER_OTLP_ENDPOINT`)

## Execução Local
- **Docker Compose** (recomendado):
  ```bash
  docker compose up -d db redis redis-init
  docker compose up -d migrations
  docker compose up -d api celery-worker celery_beat
  ```

- **Sem Docker:**
  1. Ative virtualenv e instale dependências: `pip install -r ../requirements.txt`.
  2. Configure `.env.common` e `.env.market_alert` com valores locais.
  3. Execute migrações: `alembic upgrade head`.
  4. Inicie API: `uvicorn market_alert.main:app --reload --port 8000`.
  5. Suba worker Celery: `celery -A market_alert.core.celery_app:celery_app worker --loglevel=info -Q celery,scraping,monitor`.
  6. Inicie o beat com métricas: `python market_alert/beat_with_metrics.py`.

## Testes
```bash
pytest market_alert -q
```
As suítes cobrem rotas, tasks e integrações simuladas com o scraper; utilize `-k` ou `-m` para isolar cenários específicos.

## Troubleshooting Rápido
- **Falhas ao contatar o scraper:** verifique `SCRAPER_BASE_URL`, tokens de serviço e métricas `SCRAPER_CLIENT_REQUESTS_TOTAL` em `shared/metrics`.
- **Fila Celery acumulada:** confira o estado do Redis e monitore `CELERY_TASKS_TOTAL` por fila; ajuste `concurrency` do worker conforme necessário.
- **Rate limit excedido:** erros 429 indicam configuração do `Limiter`; ajuste limites ou whitelists em `main.py`.
- **Problemas de banco:** monitore `DB_POOL_SIZE`, `DB_POOL_CHECKOUTS` (expostos em `/metrics`) e revise parâmetros de pool no `.env`.
- **Métricas ausentes**: confirme porta configurada (`METRICS_PORT`) e se `beat_with_metrics.py` está ativo.

Atualize este documento sempre que rotas, tasks, filas ou dependências forem alteradas.
