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
- **Regras de comparação e alertas**: comparações permanecem automáticas após coletas, priorizando mudanças de preço e disponibilidade sem thresholds dinâmicos ou idempotência distribuída. Fluxos manuais apenas disparam tasks já idempotentes (ex.: `compare_prices_task`).

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
| `GET` | `/monitored` | Lista monitorados usando envelope `{ items, meta }` com filtros `page`, `per_page`, `query` e `status`. O parâmetro `per_page` é opcional e, quando omitido, retorna todos os itens dentro do limite defensivo aplicado pela API.  |
| `GET` | `/monitored/{id}` | Retorna detalhes do monitorado com `owner_id`, `thumbnail`, `current_price` (`Decimal` serializado), datas derivadas (`created_at`, `last_price_change_at`) além do contador `alerts_sent`. |
| `GET` | `/monitored/featured` | Retorna até 3 monitorados em destaque respeitando `is_featured` e ordenação configurada. |
| `POST` | `/monitored/scrape` | Valida duplicidade por usuário + URL, cria recurso mínimo (`id`, `url`, `created_at`) e agenda coleta na fila `scraping`, aceitando `initial_competitor` para disparo imediato do concorrente. |
| `POST` | `/monitored` | Cria produto monitorado associado ao usuário autenticado (fluxo alternativo ao scrape imediato). |
| `GET` | `/comparisons/{monitored_id}` | Lista comparações paginadas (`items` + `meta`) para o monitorado informado. |
| `GET` | `/comparisons/{monitored_id}/summary` | Consolida métricas de comparação; `Decimal` enviado como número apenas no resumo (encoder existente). |
| `GET` | `/competitors` | Lista concorrentes vinculados a um monitorado com paginação e campos `thumbnail`/`last_scraped_at`. |
| `POST` | `/competitors/scrape` | Valida duplicidade por `monitored_id` + URL, cria recurso mínimo e agenda coleta na fila `scraping`. |
| `GET` | `/notifications` | Lista histórico e status de notificações geradas. |
| `GET` | `/metrics` | Exibe métricas Prometheus da API. |
| `Celery` | `tasks.collector_product_task.collect_product_task` | Consome fila `scraping` e processa uma URL por vez (monitorado ou concorrente), respeitando lock Redis e retornando `ScrapeResult` padronizado; quando o lock não é adquirido retorna `no_result` e registra métrica de `lock_skipped`. |
| `Celery` | `tasks.recheck_scheduler_task.schedule_rechecks` | Beat que identifica `next_check_at` vencido, recalcula o próximo horário e enfileira a `collect_product_task` diretamente com jitter leve. |
| `Celery` | `tasks.compare_prices_task.compare_prices_task` | Idempotente e leve; recalcula comparação e `competitiveness_status` quando acionado. |
| `Celery` | `tasks.alert_tasks.dispatch_price_alert_task` | Enfileira alertas quando regras de preço são acionadas. |

### Integração com os Serviços
- **`market_scraper`**: consumido por `scraper/scraper_client.ScraperClient`, que envia `ParserRequest` valida `ParserResponse` do pacote e trata `304 Not Modified` retornando `None` quando nada mudou. O `ParserResponse` retorna sempre `price|currency` (pode ser `null`), `availability`, `last_status`, `etag` e `not_modified`, permitindo marcar anúncios inativos sem gravar preços `0.00`.
- **`shared/`**: reutiliza abstrações de configuração, métricas (`shared/metrics/metrics_api.py`), segurança e utilidades comuns.
- **Infraestrutura comum**: compartilha Redis (fila Celery/cache) e Postgres definidos no `docker-compose.yml`, além do `.env.common` para logs e tracing.
- **Codificação numérica**: valores monetários são serializados como string (`Decimal` → `"1099.90"`) em quase todos os contratos, exceto no resumo de comparação que mantém encoder numérico para compatibilidade.
- **Execução das comparações**: as comparações são executadas automaticamente pelas tasks de monitoramento e comparação; não há endpoint para disparo manual.

> O canal WebSocket de notificações permanece desativado temporariamente; utilize `/notifications/logs` e polling no frontend para acompanhar alertas.

## Celery
- **Arquivo principal:** `core/celery_app.py`.
- **Filas padrão:** `celery`, `scraping`, `monitor` (configuráveis via `.env.market_alert`).
- **Tasks de destaque:**
  - `tasks.collector_product_task.collect_product_task`
  - `tasks.recheck_scheduler_task.schedule_rechecks`
  - `tasks.compare_prices_task.compare_prices_task`
  - `tasks.alert_tasks.dispatch_price_alert_task`
  - `tasks.metrics_tasks.collect_celery_metrics`, `cleanup_cache`
- **Beat com métricas:** `beat_with_metrics.py` executa agendamentos e expõe `/metrics` em porta dedicada (`8001`).

### Scraping e resiliência
- **Cliente síncrono:** `scraper/scraper_client.py` usa `httpx.Client` de vida curta e fluxo linear. Evite helpers assíncronos ou `asyncio.run` dentro das tasks para impedir erros de loop fechado.
- **Proteções:** rate limiter e circuit breaker recebem `get_redis_client` como fábrica e só tentam abrir conexão quando invocados, tolerando Redis indisponível durante o bootstrap do worker.
- **Pool do worker:** mantenha o pool `prefork` (padrão) para que `time.sleep` usado nos backoffs não bloqueie outros workers em pools baseados em threads/eventlet. Se migrar para pools cooperativos, troque os backoffs bloqueantes por `countdown` do Celery ou sleeps compatíveis com o worker escolhido.
- **Retries e erros:** tarefas de scraping aplicam `self.retry` progressivo (incluindo `429 Retry-After`) antes de marcar monitorados como `failed`. Cada falha registra `scraping_errors` com o motivo retornado pelo cliente.

## Configuração
Variáveis padrão residem em [`core/config_alert.py`](core/config_alert.py) e podem ser sobrescritas via `market_alert/.env.market_alert`.

| Categoria | Variáveis relevantes |
|-----------|----------------------|
| Banco de dados | `DATABASE_URL` |
| Autenticação | `SECRET_KEY`, `ALGORITHM`, `ACCESS_TOKEN_EXPIRE_MINUTES`, `REFRESH_TOKEN_EXPIRE_DAYS` |
| Celery | `CELERY_BROKER_URL`, `CELERY_RESULT_BACKEND`, `CELERY_TASK_ROUTES`, `CELERY_TIMEZONE`, `CELERY_BEAT_SCHEDULE_FILE` |
| Locks de produto | `PRODUCT_LOCK_TTL_SECONDS` |
| Scraper | `SCRAPER_SERVICE_URL`, `SCRAPER_CONNECT_TIMEOUT`, `SCRAPER_READ_TIMEOUT`, `SCRAPER_TOTAL_TIMEOUT`, `SCRAPER_SERVICE_AUTH_HEADER`, `SCRAPER_SERVICE_AUTH_TOKEN`, `SCRAPER_RETRY_ATTEMPTS`, `SCRAPER_RETRY_BACKOFF_MIN`, `SCRAPER_RETRY_BACKOFF_MAX` |
| Comunicação e alertas | `SMTP_HOST`, `SMTP_PORT`, `SMTP_USERNAME`, `SMTP_PASSWORD`, `SMTP_TLS`, `SMTP_FROM`, `TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN`, `TWILIO_SMS_FROM`, `TWILIO_WHATSAPP_FROM`, `FCM_SERVER_KEY` |

### Padrões de contratos
- **Paginação**: todas as rotas de listagem utilizam envelope `{ items: [], meta: { total, page, per_page } }` com paginação base 1. Quando `per_page` não é enviado em `/monitored`, a API retorna todos os registros disponíveis preservando um teto de segurança.
- **Campos monetários**: valores `Decimal` são serializados como string (`"1099.90"`) por padrão. O resumo de comparação mantém encoder que envia números (`1099.9`) e deve ser tratado pelo frontend.
- **Criar via scraping**: endpoints `/monitored/scrape` e `/competitors/scrape` retornam 202 com representação mínima do recurso (`id`, `url`, `created_at`) e enfileiram coleta na fila `scraping`.
- **Destaques**: `/monitored/featured` devolve até 3 monitorados com `is_featured=true`, ordenados pelo critério definido em `routes_monitored`.

**Semântica de timestamps de scraping**
- **`last_checked`**: registra quando o sistema tentou/processou uma checagem do produto (qualquer tentativa, sucesso ou não). Usado pelo agendador e para decisões operacionais como `SCRAPER_FORCE_REFRESH_TTL_SECONDS`.
- **`last_scraped_at`**: registra o momento em que dados novos/atualizados foram efetivamente obtidos do `market_scraper` (ou seja, quando um fetch retornou payload que representa conteúdo atualizado). Não deve ser atualizado em retornos `304 Not Modified`.
- **`checked_at`** (em `PriceHistory`): carimbo de tempo da observação/medição de preço — usado para séries históricas e determinação do instante da mudança de preço.

Observação: a implementação foi ajustada para que respostas `304 Not Modified` atualizem apenas `last_checked` (indicador de atividade), preservando `last_scraped_at` como sinal de frescor dos dados brutos.

## Principais Componentes do Serviço
- `main.py` – instancia a aplicação FastAPI, middlewares, limiter e rotas.
- `core/config_alert.py` – carrega variáveis de ambiente e aplica defaults.
- `core/celery_app.py` – configura worker, beat e registradores de métricas.
- `services/scraper_client.py` – encapsula chamadas HTTP ao `market_scraper` com autenticação.
- `services/comparison_service.py` – orquestra cálculos de comparação e dispara regras.
- `tasks/recheck_scheduler_task.py` – beat responsável por enfileirar rechecagens usando o mesmo collector.
- `tasks/alert_tasks.py` – envia notificações e aplica cooldowns.
- `tasks/metrics_tasks.py` – publica métricas periódicas da fila e recursos.
- `tasks/compare_prices_task.py` – recalcula históricos de comparação e atualiza `competitiveness_status` após scraping.

Exemplo mínimo de `.env.market_alert`:
```env
DATABASE_URL=postgresql+asyncpg://market:market@db:5432/market

REDIS_URL=redis://:senha@redis:6379/0
REDIS_PASSWORD=senha
CELERY_BROKER_URL=redis://redis:6379/0
CELERY_RESULT_BACKEND=redis://redis:6379/1
CELERY_TASK_ROUTES={"tasks.recheck_scheduler_task.*": {"queue": "monitor"}}

SCRAPER_SERVICE_URL=http://market_scraper:8010
SCRAPER_CONNECT_TIMEOUT=5.0
SCRAPER_READ_TIMEOUT=25.0
SCRAPER_TOTAL_TIMEOUT=8.0
SCRAPER_SERVICE_AUTH_HEADER=X-Internal-Token
SCRAPER_SERVICE_AUTH_TOKEN=token-exemplo

SMTP_HOST=smtp.mailtrap.io
SMTP_PORT=587
SMTP_USERNAME=usuario
SMTP_PASSWORD=senha
SMTP_TLS=1
SMTP_FROM=alerts@empresa.dev

TWILIO_ACCOUNT_SID=id_conta_twilio
TWILIO_AUTH_TOKEN=token_autenticacao_twilio
TWILIO_SMS_FROM=numeor_sms_twilio
TWILIO_WHATSAPP_FROM=whats_twilio

FCM_SERVER_KEY=chave_fcm
SLACK_WEBHOOK_URL=url_slack
SECRET_KEY=chave_secreta_jwt

ADAPTIVE_RECHECK_BASE_INTERVAL=7200
SCRAPER_SERVICE_URL=url_servico_scraping

```

## Orquestração de coletas e rechecagens
- **Collector único:** `services/collector_service.py` monta payloads mínimos e envia sempre para a fila `scraping`, consumida pela task `market_alert.tasks.collector_product_task.collect_product_task`. A task aplica um lock Redis por produto (TTL configurável via `PRODUCT_LOCK_TTL_SECONDS`), retorna `ScrapeResult` (`success`, `not_modified`, `no_result`, `error`) e dispara `compare_prices_task` apenas quando houver mudança relevante; lock não adquirido resulta em `no_result` com métrica de `lock_skipped` incrementada.
- **Rechecagem centralizada:** rechecagens usam a mesma `collect_product_task` aplicada a coletas manuais, com lock Redis e TTL automático como único mecanismo de exclusão mútua.
- **Agendamento via Beat:** `market_alert.tasks.recheck_scheduler_task.schedule_rechecks` identifica `next_check_at` vencido, recalcula o próximo horário com `_compute_next_check_at` e enfileira diretamente o collector com jitter, evitando flags ou comparações inline.
- **Persistência de histórico sem duplicidade:** retornos `not_modified` apenas atualizam timestamps e status de disponibilidade; criação de `PriceHistory` usa checagem idempotente para impedir duplicatas quando não há mudança.

## Segurança e Observabilidade
- **Segurança:**
  - JWT curto com refresh token
  - Filtragem de payloads e segregação de permissões por usuário
  - Segredos permanecem em arquivos `.env` ignorados pelo Git.

- **Política de logs e proteção de dados:**
  - Nunca registre tokens de acesso/refresh, cabeçalhos `Authorization`, códigos de verificação ou senhas; utilize apenas flags booleanas para indicar presença.
  - Não serialize ou propague variáveis de ambiente sensíveis (`SMTP_*`, `TWILIO_*`, `FCM_SERVER_KEY`, `SCRAPER_SERVICE_AUTH_TOKEN`) em mensagens de log ou respostas de API.
  - Logs devem priorizar contexto seguro (IP, status da operação, identificadores internos) e adotar `structlog` para manter rastreabilidade sem expor credenciais.
  - Em fluxos de auditoria, prefira `token_id` ou `user_id` em vez do valor cru de chaves ou tokens.

- **Observabilidade:**
  - Métricas expostas em `/metrics`
  - Logs estruturados via `structlog`
     - Métricas Celery disponíveis em `beat_with_metrics.py` na porta configurada, incluindo contadores de scraping e latência (`market_alert_monitoring_tasks_total`, `market_alert_scrape_latency_seconds`).

## Execução Local
- **Docker Compose** (recomendado):
  ```bash
  docker compose up -d db redis redis-init
  docker compose up -d migrations
  docker compose up -d api celery-worker celery_beat
  ```

- **Sem Docker:**
  1. Pré-requisitos: Python 3.11, Postgres e Redis acessíveis; instale deps com `pip install -r ../requirements.txt`.
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
- **Falhas ao contatar o scraper:** verifique `SCRAPER_SERVICE_URL`, tokens de serviço e métricas `SCRAPER_CLIENT_REQUESTS_TOTAL` em `shared/metrics`.`SCRAPER_CLIENT_REQUESTS_TOTAL` em `shared/metrics`.
- **Fila Celery acumulada:** confira o estado do Redis e monitore `CELERY_TASKS_TOTAL` por fila; ajuste `concurrency` do worker conforme necessário.
- **Rate limit excedido:** erros 429 indicam configuração do `Limiter`; ajuste limites ou whitelists em `main.py`.
- **Problemas de banco:** monitore `DB_POOL_SIZE`, `DB_POOL_CHECKOUTS` (expostos em `/metrics`) e revise parâmetros de pool no `.env`.
- **Métricas ausentes**: confirme porta exposta pelo `beat_with_metrics.py` e se o processo está ativo.

Atualize este documento sempre que rotas, tasks, filas ou dependências forem alteradas.
