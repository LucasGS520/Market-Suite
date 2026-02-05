# Market Alert
API FastAPI responsável por autenticação, gestão e monitoramento, além de comparação de preços. Opera com PostgreSQL, Redis, Celery (workers dedicados) e integra o `market_scraper` para coleta de dados.

## Relações e Referências
- Visão geral da suíte e topologia: [`../README.md`](../README.md)
- Detalhes do serviço de scraping: [`../market_scraper/README.md`](../market_scraper/README.md)
- Guia operacional para agentes: [`../AGENTS.md`](../AGENTS.md)

## Principais Responsabilidades
- **Expor rotas REST** para gerenciamento de usuários, autenticação, produtos monitorados e concorrentes, comparações.
- **Agendar tarefas Celery** (`scraping`, `monitor`, `compare`, `notifications`) para coleta de dados contínua e comparação.
- **Persistir dados** em PostgreSQL utilizando SQLAlchemy (módulos `models/` e `crud/`).
- **Registrar logs estruturados** para auditoria operacional.
- **Integrar com o `market_scraper`** usando `ScraperClient` (`services/scraper_client.py`).
- **Regras de comparação**: comparações permanecem automáticas após coletas, priorizando mudanças de preço e disponibilidade sem thresholds dinâmicos ou idempotência distribuída. Fluxos manuais apenas disparam tasks já idempotentes (ex.: `compare_prices_task`).
- **Notificações e alertas**: eventos de domínio alimentam regras configuráveis e geram notificações persistidas com idempotência e auditoria.

## Estrutura do Diretório
```text
market_alert/
├── auth/                #Fluxos de autenticação, JWT e rotas de login/refresh/reset
├── core/                #Configuração do serviço, inicialização do Celery e carregamento de env
├── crud/                #Operações de banco de dados (SQLAlcemy Session)
├── models/              #Modelos ORM (SQLAlchemy)
├── routes/              #Rotas FastAPI (usuários, monitoramentos, comparações, etc.)
├── schemas/             #Modelos Pydantic expostos pela API
├── services/            #Regras de negócio (scraper client, comparações)
├── tasks/               #Conjunto de tasks Celery (scraping, monitoramento)
└── utils/               #Auxiliares (cache, rate limiting, serialização, etc.)
```

## Endpoints e Fluxos Relevantes
| Método | Rota / Fluxo | Descrição |
|--------|--------------|-----------|
| `POST` | `/auth/login` | Autenticação via formulário e emissão de JWT. |
| `POST` | `/auth/refresh` | Renova token de acesso ativo. |
| `POST` | `/auth/verify-email` | Confirma verificação de email via token. |
| `POST` | `/auth/verify-phone` | Confirma OTP de telefone. |
| `POST` | `/auth/logout` | Revoga o refresh token informado. |
| `POST` | `/users` | Cadastro de usuário pendente com verificação. |
| `POST` | `/users/resend-verification` | Reenvia verificação de email ou telefone. |
| `GET` | `/monitored` | Lista monitorados usando envelope `{ items, meta }` com filtros `page`, `per_page`, `query` e `status`. O parâmetro `per_page` é opcional e, quando omitido, retorna todos os itens dentro do limite defensivo aplicado pela API.  |
| `GET` | `/monitored/{id}` | Retorna detalhes do monitorado com `owner_id`, `thumbnail`, `current_price` (`Decimal` serializado) e datas derivadas (`created_at`, `last_price_change_at`). |
| `GET` | `/monitored/featured` | Retorna até 3 monitorados em destaque respeitando `is_featured` e ordenação configurada. |
| `POST` | `/monitored/scrape` | Valida duplicidade por usuário + URL, cria recurso mínimo (`id`, `url`, `created_at`, `next_check_at`), dispara coleta imediata na fila `scraping` e agenda o monitorado na fila contínua de prioridade para rechecagens. |
| `POST` | `/monitored` | Cria produto monitorado associado ao usuário autenticado (fluxo alternativo ao scrape imediato). |
| `GET` | `/comparisons/{monitored_id}` | Lista comparações paginadas (`items` + `meta`) para o monitorado informado. |
| `GET` | `/comparisons/{monitored_id}/summary` | Consolida resumo de comparação; `Decimal` enviado como número apenas no resumo (encoder existente). |
| `GET` | `/competitors` | Lista todos os concorrentes vinculados (incluindo pausados e indisponíveis por padrão), aceita `include_inactive`/`include_paused` e retorna contadores `competitors_total`, `competitors_with_price_count` e `excluded_due_to_inactive_count`. |
| `POST` | `/competitors/scrape` | Valida duplicidade por `monitored_id` + URL, cria recurso mínimo, dispara coleta imediata na fila `scraping` e garante o monitorado na fila contínua de prioridade para rechecagens. |
| `GET` | `/notifications` | Lista histórico de notificações do usuário com paginação padrão. |
| `GET` | `/notifications/preferences` | Retorna preferências de notificação do usuário. |
| `POST` | `/notifications/preferences` | Cria ou atualiza preferência para canal e tipo de alerta. |
| `Celery` | `tasks.collector_product_task.collect_product_task` | Consome fila `scraping` e processa uma URL por vez (monitorado ou concorrente), respeitando lock Redis e retornando `ScrapeResult` padronizado; quando o lock não é adquirido retorna `no_result`. |
| `Celery` | `tasks.continuous_collector_task.run_continuous_collector` | Worker contínuo que consome a fila de prioridade em Redis, dispara coletas assíncronas de monitorados + concorrentes e mantém o reenqueue pendente até o término da coleta. |
| `Celery` | `tasks.compare_prices_task.compare_prices_task` | Idempotente e leve; recalcula comparação e `competitiveness_status` quando acionado. |
| `Celery` | `tasks.notifications_enqueue_task.enqueue_notifications_task` | Normaliza notificações pendentes e calcula backoff exponencial antes de novos disparos. |

### Integração com os Serviços
- **`market_scraper`**: consumido por `scraper/scraper_client.ScraperClient`, que envia `ParserRequest` valida `ParserResponse` do pacote e trata `304 Not Modified` retornando `None` quando nada mudou. O `ParserResponse` retorna sempre `price|currency` (pode ser `null`), `availability`, `last_status`, `etag` e `not_modified`, permitindo marcar anúncios inativos sem gravar preços `0.00`.
- **`shared/`**: reutiliza abstrações de configuração, segurança e utilidades comuns.
- **Infraestrutura comum**: compartilha Redis (fila Celery/cache) e Postgres definidos no `docker-compose.yml`, além do `.env.common` para logs.
- **Codificação numérica**: valores monetários são serializados como string (`Decimal` → `"1099.90"`) em quase todos os contratos, exceto no resumo de comparação que mantém encoder numérico para compatibilidade.
- **Execução das comparações**: as comparações são executadas automaticamente pelas tasks de monitoramento e comparação; não há endpoint para disparo manual.

## Celery - Arquitetura de Workers e Filas

### Organização por Workers Dedicados
O sistema utiliza **quatro workers Celery separados**, cada um consumindo uma fila específica e executando em containers ou processos independentes:

| Worker | Fila(s) | Concorrência | Responsabilidades |
|--------|---------|--------------|-------------------|
| **celery-worker-scraping** | `celery,scraping` | 4 | Executa `collect_product_task` (scraping de um monitorado/concorrente por vez) |
| **celery-worker-monitor** | `monitor` | 4 | Executa o loop contínuo `run_continuous_collector` |
| **celery-worker-compare** | `compare` | 2 | Executa `compare_prices_task` para comparação assíncrona |
| **celery-worker-notifications** | `notifications` | 2 | Executa `send_notification_task` + `verification_tasks` |

### Arquivo principal
- **`core/celery_app.py`**: instancia e configura o app Celery, inicializa conectores.
- **`core/celery_schedule.py`**: centraliza declarações de filas, rotas e agendamentos Beat.

### Impacto da concorrência Workers
Reduzir a concorrência do `celery-worker-*` diminui picos de requisições simultâneas contra o `market_scraper` e hosts externos, ajudando a mitigar `429` e falhas por excesso de requisições. Em contrapartida, o tempo total para processar filas de scraping pode aumentar em momentos de alta demanda.

### Tasks de destaque
- **`tasks.collector_product_task.collect_product_task`** (fila `scraping`): coleta um monitorado ou concorrente por vez com lock Redis.
- **`tasks.continuous_collector_task.run_continuous_collector`** (fila `monitor`): **task que roda indefinidamente**, consome fila de prioridade Redis, despacha monitorado+concorrentes para a fila `scraping` e só reenfileira quando o processamento expira/é reconciliado.
- **`tasks.compare_prices_task.compare_prices_task`** (fila `compare`): dispara automaticamente após coletas com mudanças.
- **`tasks.send_notification_task.send_notification_task`** (fila `notifications`): entrega alertas com retry.
- **`tasks.maintenance_tasks.cleanup_cache`** (agendada via Beat): limpa cache expirado.

### Autostart do Coletor Contínuo
O worker `celery-worker-monitor` define a variável de ambiente `CONTINUOUS_COLLECTOR_AUTOSTART=1`, que faz com que a task `run_continuous_collector` seja iniciada automaticamente quando o worker inicia. Em falhas, a task é reexecutada pelo mecanismo de retry configurado no Celery. Mantenha **apenas uma instância ativa** do loop contínuo por ambiente; o lock distribuído do coletor garante exclusividade e evita múltiplos `continuous_loop_iteration` no mesmo intervalo.

### Separação de carga entre monitoramento e comparação
As comparações foram movidas para a fila `compare`, garantindo que o worker de monitoramento permaneça dedicado ao loop contínuo e evitando saturação quando há muitas mudanças simultâneas.

### Scraping e Coleta Contínua
- **Cliente síncrono:** `services/scraper_client.py` usa `httpx.Client` de vida curta e fluxo linear. Evite helpers assíncronos ou `asyncio.run` dentro das tasks para impedir erros de loop fechado.
- **Proteções:** rate limiter e circuit breaker recebem `get_redis_client` como fábrica e só tentam abrir conexão quando invocados, tolerando Redis indisponível durante o bootstrap do worker.
- **Pool do worker:** mantenha o pool `prefork` (padrão) para que `time.sleep` usado nos backoffs não bloqueie outros workers em pools baseados em threads/eventlet. Se migrar para pools cooperativos, troque os backoffs bloqueantes por `countdown` do Celery ou sleeps compatíveis com o worker escolhido.
- **Retries e erros:** tarefas de scraping aplicam `self.retry` progressivo (incluindo `429 Retry-After`) antes de marcar monitorados como `failed`. Cada falha registra `scraping_errors` com o motivo retornado pelo cliente.
- **Locks Redis:** apenas o `collect_product_task` aplica `acquire_product_lock` com TTL configurável via `PRODUCT_LOCK_TTL_SECONDS`, evitando race conditions entre workers sem usar flags no banco.
- **Fila de Prioridade:** o `run_continuous_collector` consome um Redis Sorted Set (`PRIORITY_QUEUE_KEY`) ordenado por timestamp. Monitorados ficam em processamento enquanto as coletas assíncronas rodam; o reenqueue ocorre quando a coleta termina e a fila reavalia o `next_check_at`.

## Configuração
Variáveis padrão residem em [`core/config_alert.py`](core/config_alert.py) e podem ser sobrescritas via `market_alert/.env.market_alert`.

### Persistência do Redis
O Redis do `docker-compose.yml` utiliza AOF com snapshots para manter filas Celery e dados de cache entre reinícios. O volume `redis-data` armazena o diretório `/data`, garantindo retenção em restarts comuns. Remover volumes com `docker compose down -v` apaga o estado persistido, e uso intenso pode aumentar I/O e exigir monitoramento de disco para evitar degradação ou indisponibilidade por falta de espaço.

### Cookies de refresh em ambiente local
- Para frontend rodando em outro host/porta HTTP, defina `REFRESH_TOKEN_COOKIE_SECURE=0` e `REFRESH_TOKEN_COOKIE_SAMESITE=none`.
- Ajuste `REFRESH_TOKEN_COOKIE_NAME` e `REFRESH_TOKEN_COOKIE_PATH` apenas se houver necessidade de múltiplos ambientes ou rotas específicas.
- Configure `FRONTEND_ORIGINS` com as origens permitidas para CORS (lista separada por vírgula).

| Categoria | Variáveis relevantes |
|-----------|----------------------|
| Banco de dados | `DATABASE_URL` |
| Autenticação | `SECRET_KEY`, `ALGORITHM`, `ACCESS_TOKEN_EXPIRE_MINUTES`, `REFRESH_TOKEN_EXPIRE_DAYS`, `REFRESH_TOKEN_COOKIE_NAME`, `REFRESH_TOKEN_COOKIE_PATH`, `REFRESH_TOKEN_COOKIE_SECURE`, `REFRESH_TOKEN_COOKIE_SAMESITE`, `FRONTEND_ORIGINS` |
| Verificação | `EMAIL_VERIFICATION_EXPIRE_MINUTES`, `PHONE_VERIFICATION_EXPIRE_MINUTES`, `PHONE_VERIFICATION_MAX_ATTEMPTS`, `VERIFICATION_RESEND_INTERVAL_SECONDS`, `VERIFICATION_RESEND_MAX_PER_HOUR`, `REGISTRATION_MAX_PER_HOUR` |
| Celery | `CELERY_BROKER_URL`, `CELERY_RESULT_BACKEND`, `CELERY_TASK_ROUTES`, `CELERY_TIMEZONE`, `CELERY_BEAT_SCHEDULE_FILE` |
| Locks de produto | `PRODUCT_LOCK_TTL_SECONDS` |
| Agendamento contínuo | `CONTINUOUS_COLLECTOR_AUTOSTART`, `CONTINUOUS_COLLECTOR_LOCK_TTL_SECONDS`, `COLLECT_INTERVAL_UNSTABLE_MIN`, `COLLECT_INTERVAL_UNSTABLE_MAX`, `COLLECT_INTERVAL_STABLE_MIN`, `COLLECT_INTERVAL_STABLE_MAX`, `COLLECT_INTERVAL_VERY_STABLE_MIN`, `COLLECT_INTERVAL_VERY_STABLE_MAX`, `STABILITY_DAYS_UNSTABLE`, `STABILITY_DAYS_STABLE`, `STABILITY_DAYS_VERY_STABLE`, `CONTINUOUS_WORKER_POLL_INTERVAL`, `CONTINUOUS_WORKER_BATCH_SIZE`, `CONTINUOUS_WORKER_IDLE_SLEEP`, `CONTINUOUS_WORKER_PROCESSING_TTL_SECONDS`, `PRIORITY_QUEUE_KEY`, `PRIORITY_QUEUE_PROCESSING_KEY` |
| Scraper | `SCRAPER_SERVICE_URL`, `SCRAPER_CONNECT_TIMEOUT`, `SCRAPER_READ_TIMEOUT`, `SCRAPER_TOTAL_TIMEOUT`, `SCRAPER_SERVICE_AUTH_HEADER`, `SCRAPER_SERVICE_AUTH_TOKEN`, `SCRAPER_RETRY_ATTEMPTS`, `SCRAPER_RETRY_BACKOFF_MIN`, `SCRAPER_RETRY_BACKOFF_MAX`, `SCRAPER_HOST_RATE_LIMIT`, `SCRAPER_HOST_RATE_WINDOW_SECONDS`, `SCRAPER_HOST_RETRY_MAX_ATTEMPTS`, `SCRAPER_HOST_RETRY_WINDOW_SECONDS`, `SCRAPER_RATE_LIMIT_COOLDOWN_SECONDS`, `SCRAPER_INVALID_URL_MAX_ATTEMPTS`, `SCRAPER_INVALID_URL_TTL_SECONDS` |
| Notificações | `DEFAULT_COOLDOWN_SECONDS`, `MIN_PRICE_DELTA_PERCENT`, `NOTIFICATION_MAX_ATTEMPTS`, `NOTIFICATION_BACKOFF_BASE_SECONDS`, `NOTIFICATION_BACKOFF_MULTIPLIER`, `NOTIFICATION_DEDUPE_SENT_WINDOW_SECONDS`, `NOTIFICATION_EMAIL_PROVIDER`, `NOTIFICATION_SMS_PROVIDER`, `NOTIFICATION_WHATSAPP_PROVIDER`, `NOTIFICATION_PUSH_PROVIDER`, `NOTIFICATION_WEBHOOK_TIMEOUT_SECONDS` |

### Padrões de contratos
- **Paginação**: todas as rotas de listagem utilizam envelope `{ items: [], meta: { total, page, per_page } }` com paginação base 1. Quando `per_page` não é enviado em `/monitored`, a API retorna todos os registros disponíveis preservando um teto de segurança.
- **Campos monetários**: valores `Decimal` são serializados como string (`"1099.90"`) por padrão. O resumo de comparação mantém encoder que envia números (`1099.9`) e deve ser tratado pelo frontend.
- **Criar via scraping**: o endpoint `/monitored/scrape` retorna 202 com representação mínima do recurso (`id`, `url`, `created_at`, `next_check_at`), dispara coleta imediata na fila `scraping` e agenda o monitorado na fila contínua para rechecagens. O endpoint `/competitors/scrape` retorna 202 com o payload mínimo e enfileira coleta na fila `scraping`.
- **Destaques**: `/monitored/featured` devolve até 3 monitorados com `is_featured=true`, ordenados pelo critério definido em `routes_monitored`.

**Semântica de timestamps de scraping**
- **`last_checked`**: registra quando o sistema tentou/processou uma checagem do produto (qualquer tentativa, sucesso ou não). Usado pelo worker contínuo e para decisões operacionais como `SCRAPER_FORCE_REFRESH_TTL_SECONDS`.
- **`last_scraped_at`**: registra o momento em que dados novos/atualizados foram efetivamente obtidos do `market_scraper` (ou seja, quando um fetch retornou payload que representa conteúdo atualizado). Não deve ser atualizado em retornos `304 Not Modified`.
- **`collected_at`**: marca o instante real em que a extração foi concluída para monitorado/concorrente, servindo de base para filas contínuas.
- **`enqueued_at`**: horário em que o monitorado foi colocado na fila de prioridade, usado para latência de consumo (registrado via Redis e logs).
- **`persisted_at`**: horário em que o resultado do scraping foi confirmado no banco (registrado em logs estruturados).
- **`checked_at`** (em `PriceHistory`): carimbo de tempo da observação/medição de preço — usado para séries históricas e determinação do instante da mudança de preço.

Observação: a implementação foi ajustada para que respostas `304 Not Modified` atualizem apenas `last_checked` (indicador de atividade), preservando `last_scraped_at` como sinal de frescor dos dados brutos.

## Principais Componentes do Serviço
- `main.py` – instancia a aplicação FastAPI, middlewares, limiter e rotas.
- `core/config_alert.py` – carrega variáveis de ambiente e aplica defaults.
- `core/celery_app.py` – configura workers e rotinas de suporte.
- `services/scraper_client.py` – encapsula chamadas HTTP ao `market_scraper` com autenticação.
- `services/comparison_service.py` – orquestra cálculos de comparação.
- `tasks/continuous_collector_task.py` – worker contínuo que consome a fila de prioridade e despacha coletas assíncronas para `scraping`.
- `tasks/maintenance_tasks.py` – executa rotinas de limpeza periódicas.
- `tasks/compare_prices_task.py` – recalcula históricos de comparação e atualiza `competitiveness_status` após scraping.

Exemplo mínimo de `.env.market_alert`:
```env
DATABASE_URL=postgresql+asyncpg://market:market@db:5432/market

REDIS_URL=redis://:senha@redis:6379/0
REDIS_PASSWORD=senha
CELERY_BROKER_URL=redis://redis:6379/0
CELERY_RESULT_BACKEND=redis://redis:6379/1
CELERY_TASK_ROUTES={"tasks.continuous_collector_task.*": {"queue": "monitor"}}

SCRAPER_SERVICE_URL=http://market_scraper:8010
SCRAPER_CONNECT_TIMEOUT=5.0
SCRAPER_READ_TIMEOUT=25.0
SCRAPER_TOTAL_TIMEOUT=8.0
SCRAPER_SERVICE_AUTH_HEADER=X-Internal-Token
SCRAPER_SERVICE_AUTH_TOKEN=token-exemplo
SCRAPER_HOST_RATE_LIMIT=20
SCRAPER_HOST_RATE_WINDOW_SECONDS=60
SCRAPER_HOST_RETRY_MAX_ATTEMPTS=4
SCRAPER_HOST_RETRY_WINDOW_SECONDS=60
SCRAPER_RATE_LIMIT_COOLDOWN_SECONDS=600
SCRAPER_INVALID_URL_MAX_ATTEMPTS=3
SCRAPER_INVALID_URL_TTL_SECONDS=86400

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

REFRESH_TOKEN_COOKIE_NAME=refresh_token
REFRESH_TOKEN_COOKIE_PATH=/
REFRESH_TOKEN_COOKIE_SECURE=0
REFRESH_TOKEN_COOKIE_SAMESITE=none
FRONTEND_ORIGINS=http://localhost:5173

COLLECT_INTERVAL_UNSTABLE_MIN=120
COLLECT_INTERVAL_UNSTABLE_MAX=300
COLLECT_INTERVAL_STABLE_MIN=300
COLLECT_INTERVAL_STABLE_MAX=900
COLLECT_INTERVAL_VERY_STABLE_MIN=600
COLLECT_INTERVAL_VERY_STABLE_MAX=1800

STABILITY_DAYS_UNSTABLE=1
STABILITY_DAYS_STABLE=3
STABILITY_DAYS_VERY_STABLE=7

CONTINUOUS_WORKER_POLL_INTERVAL=1.0
CONTINUOUS_WORKER_BATCH_SIZE=20
CONTINUOUS_WORKER_IDLE_SLEEP=2.0
CONTINUOUS_WORKER_PROCESSING_TTL_SECONDS=900

CONTINUOUS_COLLECTOR_AUTOSTART=1
CONTINUOUS_COLLECTOR_AUTOSTART_TTL=60
CONTINUOUS_COLLECTOR_LOCK_TTL_SECONDS=45

PRIORITY_QUEUE_KEY=market_alert:priority_queue
PRIORITY_QUEUE_PROCESSING_KEY=market_alert:priority_queue:processing

DEFAULT_COOLDOWN_SECONDS=1800
MIN_PRICE_DELTA_PERCENT=1.0
NOTIFICATION_MAX_ATTEMPTS=3
NOTIFICATION_BACKOFF_BASE_SECONDS=60
NOTIFICATION_BACKOFF_MULTIPLIER=2

```

## Orquestração de coletas e rechecagens
- **Collector único:** `services/collector_service.py` monta payloads mínimos e envia sempre para a fila `scraping`, consumida pela task `market_alert.tasks.collector_product_task.collect_product_task`. A task aplica um lock Redis por produto (TTL configurável via `PRODUCT_LOCK_TTL_SECONDS`), retorna `ScrapeResult` (`success`, `not_modified`, `no_result`, `error`) e dispara `compare_prices_task` apenas quando houver mudança relevante; lock não adquirido resulta em `no_result`.
- **Fila contínua:** `market_alert.tasks.continuous_collector_task.run_continuous_collector` consome o Redis Sorted Set em loop, despacha monitorado + concorrentes para a fila `scraping` e deixa o reenqueue para o pós-coleta.
- **Persistência de histórico sem duplicidade:** retornos `not_modified` apenas atualizam timestamps e status de disponibilidade; criação de `PriceHistory` usa checagem idempotente para impedir duplicatas quando não há mudança.

## Troubleshooting do coletor contínuo
- **Worker monitor parado**: confirme o processo/container `celery-worker-monitor` ativo e o `CONTINUOUS_COLLECTOR_AUTOSTART=1` configurado.
- **Fila sem itens prontos**: verifique `PRIORITY_QUEUE_KEY` e se `next_check_at` está no passado.
- **Redis indisponível**: logs com `continuous_queue_unavailable` indicam falha de conexão ou credenciais.
- **Itens presos em processamento**: o loop reaproveita itens expirados usando `CONTINUOUS_WORKER_PROCESSING_TTL_SECONDS`; revise logs `continuous_processing_reclaimed`.
- **Reenqueue pendente pós-coleta**: logs de reenqueue ajudam a identificar itens mantidos em processamento enquanto as coletas assíncronas rodam.
- **Reinícios por limites de tempo**: confirme nos logs se o coletor foi reiniciado por limites de execução. O coletor contínuo usa `soft_time_limit=None` e `time_limit=None` por ser um loop infinito; ajustes de timeout devem ser feitos explicitamente na task quando necessário.
- **Autostart com throttling**: logs de autostart indicam bloqueio por cooldown; valide o TTL de autostart e a estabilidade do Redis.
- **Monitorados pausados**: itens pausados não retornam à fila; retome manualmente para reativar a coleta.

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
  - Logs estruturados via `structlog`

## Fluxo de Orquestração Completo

### 1. Criação de Monitorado
```
POST /monitored/scrape
  ↓
Valida duplicidade por usuário + URL
  ↓
Cria recurso mínimo (id, url, created_at, next_check_at)
  ↓
Dispara collect_product_task na fila "scraping"
  ↓
Agenda monitorado na fila de prioridade Redis para rechecagens contínuas
  ↓
Responde 202 com id e dados mínimos
```

### 2. Coleta Imediata (na fila scraping)
```
collect_product_task (worker: celery-worker-scraping)
  ↓
Valida payload (tipo, IDs, URL)
  ↓
Tenta adquirir lock Redis (product_lock)
  ├─ Lock adquirido: continua
  └─ Lock não adquirido: retorna "no_result"
  ↓
Chama scraper_client.scrape() → market_scraper
  ↓
Recebe ScrapeResult (success/not_modified/no_result/error)
  ↓
Persiste em PriceHistory se houver nova informação
  ↓
Retorna ao banco com resultado
```

### 3. Loop Contínuo (na fila monitor)
```
run_continuous_collector (worker: celery-worker-monitor - LOOP INFINITO)
  ↓
Enquanto não atingir soft_time_limit (≈3600s):
  ├─ Consome fila de prioridade Redis (Sorted Set)
  ├─ Pop item com timestamp <= agora
  ├─ Se nenhum item pronto: sleep adaptativo, seguindo a configuração do worker
  │
  └─ Se item encontrado:
      ├─ Carrega monitorado do DB
      ├─ Coleta_product (com lock) → ScrapeResult
      ├─ Carrega concorrentes do DB
      ├─ Para cada concorrente:
      │   └─ Coleta_product (com lock) → ScrapeResult
      ├─ Recalcula stability_score baseado em histórico de mudanças
      ├─ Calcula next_check_at (mais estável = menos frequente)
      ├─ Se houver mudanças: dispara compare_prices_task
      ├─ Persiste em DB
      └─ Reenfileira para próxima coleta com next_check_at
  ↓
Graceful shutdown: drain fila de processamento
```

### 4. Comparação e Notificações
```
compare_prices_task (fila compare, disparada automaticamente)
  ↓
Recalcula competitividade do monitorado vs concorrentes
  ↓
Atualiza competitiveness_status (Competitivo/Atenção/Urgente/Sem concorrentes)
  ↓
Gera eventos de domínio (PriceDropped, PriceIncreased, etc.)
  ↓
Notificações são enfileiradas em fila "notifications"
  ↓
send_notification_task (worker: celery-worker-notifications)
  ├─ Resolve canal preferido do usuário
  ├─ Tenta envio (email/SMS/webhook/push)
  ├─ Se falha: retry com backoff exponencial
  └─ Registra em notification_attempt
```

## Execução Local
- **Docker Compose** (recomendado):
  ```bash
  docker compose up -d db redis redis-init
  docker compose up -d migrations
  docker compose up -d api market_scraper celery-worker-scraping celery-worker-monitor celery-worker-notifications
  ```

- **Sem Docker:**
  1. Pré-requisitos: Python 3.11, Postgres e Redis acessíveis; instale deps com `pip install -r ../requirements.txt`.
  2. Configure `.env.common` e `.env.market_alert` com valores locais.
  3. Execute migrações: `alembic upgrade head`.
  4. Inicie API: `uvicorn market_alert.main:app --reload --port 8000`.
  5. Inicie Scraper: `uvicorn market_scraper.main:app --reload --port 8010`.
  6. Inicie worker scraping: `celery -A market_alert.core.celery_app:celery_app worker --loglevel=info --pool=prefork -Q celery,scraping`.
  7. Inicie worker monitor: `CONTINUOUS_COLLECTOR_AUTOSTART=1 celery -A market_alert.core.celery_app:celery_app worker --loglevel=info --pool=prefork -Q monitor`.
  8. Inicie worker notificações: `celery -A market_alert.core.celery_app:celery_app worker --loglevel=info --pool=prefork -Q notifications`.
  6. Suba worker do coletor contínuo: `celery -A market_alert.core.celery_app:celery_app worker --loglevel=info -Q monitor`.
  7. Suba worker de notificações: `celery -A market_alert.core.celery_app:celery_app worker --loglevel=info -Q notifications`.

## Testes
```bash
pytest market_alert -q
```
As suítes cobrem rotas, tasks e integrações simuladas com o scraper; utilize `-k` ou `-m` para isolar cenários específicos.

## Troubleshooting Rápido
- **Falhas ao contatar o scraper:** verifique `SCRAPER_SERVICE_URL` e tokens de serviço.
- **Fila Celery acumulada:** confira o estado do Redis e monitore `CELERY_TASKS_TOTAL` por fila; ajuste `concurrency` do worker conforme necessário.
- **Rate limit excedido:** erros 429 indicam configuração do `Limiter`; ajuste limites ou whitelists em `main.py`.
- **Problemas de banco:** revise parâmetros de pool no `.env`.
- **Métricas ausentes**: confirme porta exposta pelos workers e se os processos estão ativos.

Atualize este documento sempre que rotas, tasks, filas ou dependências forem alteradas.
