# Market Alert
API FastAPI que centraliza autenticação, cadastro de monitoramentos, comparação de preços e disparo de notificações. A aplicação integra PostgreSQL, Redis e Celery (worker + beat) e consome o `market_scraper` via cliente HTTP dedicado.

## Relações e Referências
- Visão geral da suíte e topologia: [`../README.md`](../README.md)
- Detalhes do scraper consumido pela API: [`../market_scraper/README.md`](../market_scraper/README.md)

## Principais Responsabilidades
- **Expor rotas REST** para gerenciamento de usuários, produtos monitorados, concorrentes e configurações de alertas.
- **Agendar tarefas Celery** (`scraping`, `monitor`, `metrics`) para coleta de dados, comparações e notificações.
- **Persistir dados** em PostgreSQL utilizando SQLAlchemy (módulos `models/` e `crud/`).
- **Registrar métricas e logs estruturados** para Prometheus e Loki.
- **Integrar com o `market_scraper`** usando `ScraperClient` (`services/scraper_client.py`).

## Estrutura do Diretório
```text
market_alert/
├── auth/                # Fluxos de autenticação, JWT, rotas de login/refresh/reset
├── core/                # Configuração, inicialização do Celery e carregamento de env
├── crud/                # Operações de banco de dados
├── models/              # ORM (SQLAlchemy)
├── routes/              # Rotas FastAPI (usuários, monitoramentos, notificações, etc.)
├── schemas/             # Modelos Pydantic expostos pela API
├── services/            # Regras de negócio (scraper client, comparações, notificações)
├── tasks/               # Conjunto de tasks Celery (monitoramento, métricas, alertas)
├── notifications/       # Templates e canais de notificação
├── templates/           # E-mails e mensagens HTML/texto
└── utils/               # Auxiliares (cache, rate limiting, etc.)
```

## Endpoints e Fluxos Relevantes
- **Auth** (`/auth`, `/auth/refresh`, `/auth/logout`, `/auth/profile`, `/auth/reset-password`): login com JWT, refresh e gerenciamento de credenciais.
- **Monitoramentos** (`/monitored`, `/monitored/{id}`, `/monitored/scrape`): CRUD de produtos monitorados e acionamento manual de scraping.
- **Concorrentes** (`/competitors`, `/competitors/{monitored_id}`, `/competitors/scrape`): gestão de URLs concorrentes vinculadas a um monitorado.
- **Comparações** (`/comparisons/{monitored_id}/run`): executa comparação imediata e retorna agregados.
- **Alertas e notificações** (`/alerts`, `/notifications`): consulta histórico e configurações.
- **Saúde e métricas** (`/health/ping`, `/metrics`): status da API e métricas Prometheus.

Todas as rotas utilizam modelos Pydantic de `schemas/`. O throttling básico é aplicado pelo `Limiter` configurado em `main.py`.

## Integração com o Scraper
1. Rotas como `POST /monitored/scrape` chamam `services/scraper_client.ScraperClient`.
2. O cliente monta `ParseRequest` com base no schema da API e envia ao endpoint `/scraper/parse`.
3. Respostas `ParseResponse` são persistidas em `crud/` e podem disparar tasks de comparação.
4. Cenários `304 Not Modified` ou `no_result` são tratados para evitar escrita desnecessária.
5. Erros HTTP e de parsing são registrados em tabelas de auditoria e expõem métricas em `shared/metrics/metrics_api.py`.

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

| Categoria | Exemplos de variáveis |
|-----------|-----------------------|
| Banco de dados | `DATABASE_URL`, `SQLALCHEMY_POOL_SIZE`, `SQLALCHEMY_MAX_OVERFLOW` |
| Celery | `CELERY_BROKER_URL`, `CELERY_RESULT_BACKEND`, `CELERY_TASK_ROUTES`, `CELERY_TIMEZONE` |
| Scraper | `SCRAPER_BASE_URL`, `SCRAPER_TIMEOUT_SECONDS`, `SCRAPER_SERVICE_AUTH_HEADER`, `SCRAPER_SERVICE_AUTH_TOKEN` |
| Notificações | `NOTIFICATION_FROM_EMAIL`, `NOTIFICATION_WEBHOOK_URL`, `NOTIFICATION_COOLDOWN_SECONDS` |
| Observabilidade | `OTEL_EXPORTER_OTLP_ENDPOINT`, `SERVICE_NAME`, flags para métricas/logs |

`.env.common` complementa configurações compartilhadas (Redis, logging, tracing). Sempre referencie o exemplo mantido na raiz do projeto.

## Execução Local
- **Docker Compose** (recomendado):
  ```bash
  docker compose up -d db redis redis-init
  docker compose up -d migrations
  docker compose up -d api celery-worker celery_beat
  ```
- **Sem Docker:**
  1. Ative a virtualenv e instale dependências (`pip install -r ../requirements.txt`).
  2. Configure `.env.common` e `.env.market_alert`.
  3. Rode migrações: `alembic upgrade head`.
  4. Inicie a API: `uvicorn market_alert.main:app --reload --port 8000`.
  5. Inicie o worker: `celery -A market_alert.core.celery_app:celery_app worker --loglevel=info --pool=threads --concurrency=4 -Q celery,scraping,monitor`.
  6. Inicie o beat com métricas: `python market_alert/beat_with_metrics.py`.

## Testes
```bash
pytest market_alert -q
```
Fixtures cobrem rotas, tasks e integração com o scraper (mocks HTTP). Utilize marcadores específicos (`-k`, `-m`) para focar cenários.

## Troubleshooting Rápido
- **Falhas ao contatar o scraper:** verifique `SCRAPER_BASE_URL`, tokens de serviço e métricas `SCRAPER_CLIENT_REQUESTS_TOTAL` em `shared/metrics`.
- **Fila acumulada:** confira o estado do Redis e monitore `CELERY_TASKS_TOTAL` por fila; ajuste `concurrency` do worker conforme necessário.
- **Rate limit excedido:** erros 429 indicam configuração do `Limiter`; ajuste limites ou whitelists em `main.py`.
- **Problemas de banco:** monitore `DB_POOL_SIZE`, `DB_POOL_CHECKOUTS` (expostos em `/metrics`) e revise parâmetros de pool no `.env`.

Atualize este documento sempre que rotas, tasks, filas ou dependências forem alteradas.
