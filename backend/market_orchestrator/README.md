# Market Orchestrator
módulo Python responsavel pelo plano de controle durável do monitoramento continuo de cada produto monitorado. O `market_orchestrator` usa Temporal para decidir quando coletar, quando retentar, quando pausar e quando encerrar, enquanto a execucao concreta de coleta continua no ecossistema `market_alert` (Celery + Redis + PostgreSQL).

O módulo não expõe API HTTP propria. Ele funciona como camada de orquestração de estado e tempo.

## Relacoes e Referencias
- Visão arquitetural da suite: [`../README.md`](../README.md)
- Serviço executor de negócio (API + Celery): [`../market_alert/README.md`](../market_alert/README.md)
- Serviço de scraping consumido indiretamente: [`../market_scraper/README.md`](../market_scraper/README.md)

## Principais Responsabilidades
- **Orquestrar o ciclo continuo de monitoramento** com workflow durável por monitorado (`workflow_id = monitored:{id}`).
- **Separar decisao de execucao**: workflow decide estados e temporização; activities fazem I/O (DB, Redis, enqueue Celery).
- **Garantir reação a eventos de ciclo de vida** via signals (`pause`, `resume`, `delete`, `competitor_changed`, `update_policy`).
- **Persistir snapshot operacional** do estado do workflow no Redis para observabilidade.
- **Expor contracts, workflow e activities para execucao do worker Temporal** sem depender de `market_alert`.

## Estrutura do Diretório
```text
market_orchestrator/
|-- activities/                 # Activities de I/O (bridge Temporal <-> dominio)
|   |-- dispatch_activity.py    # Enfileira coleta no market_alert
|   |-- status_activity.py      # Consulta status de coleta no banco de negocio
|   |-- snapshot_activity.py    # Persiste/limpa snapshot no Redis
|   |-- policy_activity.py      # Le politica atual do monitorado
|   `-- __init__.py             # Exporta activities para registro no worker
|-- core/
|   `-- config_orchestrator.py  # OrchestratorSettings e variaveis de ambiente
|-- enums/
|   `-- enums_workflow.py       # WorkflowState
|-- schemas/                    # Dataclasses de input/signals/snapshot/policy
|-- workflow.py                 # MonitoredProductWorkflow (deterministico)
|-- worker.py                   # Bootstrap do Temporal Worker
|-- requirements-orchestrator.txt
`-- .env.market_orchestrator
```

---

## Arquitetura do módulo

### Modelo "orquestrador + executor"
- **Plano de controle (Temporal / market_orchestrator)**: decide fluxo, temporizacao, retry/backoff e transicoes de estado.
- **Plano de execução (market_alert + Celery)**: executa coleta, comparação e notificação.

Essa separação preserva o pipeline operacional existente e adiciona governança duravel ao ciclo de monitoramento.

### Componentes Centrais
- [`workflow.py`](workflow.py): implementa `MonitoredProductWorkflow` com loop de estados e regras de determinismo (sem I/O direto).
- [`activities/`](activities/): camada de integração externa chamada pelo workflow.
- [`worker.py`](worker.py): registra workflow + activities na task queue Temporal configurada.
- [`core/config_orchestrator.py`](core/config_orchestrator.py): configuração central e validações de ambiente.
- Cliente Temporal canônico consumido pelo domínio: [`../shared/clients/temporal/orchestrator_client.py`](../shared/clients/temporal/orchestrator_client.py).
- Reconciliação de workflows: [`../market_alert/infraestructure/temporal/reconciler.py`](../market_alert/infraestructure/temporal/reconciler.py), acionada pelo startup da API e pela task periódica de `market_alert`.

### Estados do Workflow
| Estado | Papel | Transições principais |
|--------|-------|-----------------------|
| `WaitingTimer` | Aguarda proxima janela de coleta (`next_check_at` ou policy interval) | `Dispatching`, `Paused`, `CompletedDeleted` |
| `Dispatching` | Executa `dispatch_collection` | `WaitingResult` ou `Backoff` |
| `WaitingResult` | Polling de conclusão via `query_collection_status` | `WaitingTimer`, `Paused`, `Backoff`, `CompletedDeleted` |
| `Backoff` | Retry com atraso exponencial | `Dispatching` ou `FailedTerminal` |
| `Paused` | Congela ciclo ate signal de resume | `WaitingTimer`, `Dispatching`, `CompletedDeleted` |
| `FailedTerminal` | Estado final de falha apos limite de tentativas | encerra workflow |
| `CompletedDeleted` | Estado final apos delete/cleanup | encerra workflow |

`Continue-As-New` e aplicado preventivamente quando `WORKFLOW_HISTORY_LENGTH_LIMIT` ou `WORKFLOW_SIGNAL_COUNT_LIMIT` e atingido.

### Signals e Query
| Tipo | Nome | Efeito |
|------|------|--------|
| Signal | `pause` | Move para `Paused` |
| Signal | `resume` (`ResumeSignalPayload`) | Retoma workflow; pode forçar coleta imediata |
| Signal | `delete` | Executa cleanup e finaliza em `CompletedDeleted` |
| Signal | `competitor_changed` (`CompetitorChangedPayload`) | Preempte timer para acordar ciclo |
| Signal | `update_policy` (`UpdatePolicySignalPayload`) | Atualiza policy para proximos ciclos |
| Query | `get_state` | Retorna `WorkflowSnapshot` |

### Activities de Integração

Todas as activities retornam tipos tipados de `shared.schemas.shared_schemas_orchestrator` e acessam o banco de negócio via SQL direto (`sqlalchemy.text`), sem importar modelos ORM de `market_alert`.

| Activity | Funcao | Retorno | Integração principal |
|----------|--------|---------|----------------------|
| `dispatch_collection` | Busca URL do monitorado no BD e enfileira coleta | `DispatchActivityOutput` | SQL direto em `monitored_products`; `shared.clients.celery.task_dispatcher.send_collection_task()` — sem import de `market_alert` |
| `query_collection_status` | Infere conclusão da coleta comparando `last_scraped_at` com o timestamp de dispatch | `QueryStatusOutput` | SQL direto em `monitored_products`; timestamp de dispatch lido do Redis |
| `fetch_monitored_policy` | Calcula agendamento real baseado em estabilidade | `PolicyActivityOutput` | SQL direto em `monitored_products`; `shared.scheduling.calculate_schedule()` |
| `persist_workflow_snapshot` | Salva snapshot de estado no Redis | `None` | chave `workflow:snapshot:{monitored_id}` |
| `cleanup_workflow_state` | Remove estado transitário | `None` | delete da chave de snapshot |

**Timeouts e retries das activities** (configurados em `core/config_orchestrator.py`):

| Activity | Timeout | Retry |
|----------|---------|-------|
| `dispatch_collection` | 30s (`ACTIVITY_DISPATCH_TIMEOUT_SECONDS`) | 5 tentativas, backoff 10s→5min |
| `query_collection_status` | 15s | 5 tentativas |
| `fetch_monitored_policy` | 15s | 5 tentativas |
| `persist_workflow_snapshot` | 10s | 5 tentativas |
| `cleanup_workflow_state` | 10s | 5 tentativas |

**Responsabilidade de retry por camada (não misturar):**
- **Temporal** (`_DEFAULT_RETRY` em `workflow.py`): retentar falhas de *activity* (Redis temporariamente indisponível, timeout de DB).
- **Celery** (`COLLECTION_RETRY` em `retry_policies.py`): retentar falhas de *execução de scraping* (lock concorrente, I/O HTTP).

---

## Integração com Market Alert e Market Scraper

### Integrações do `market_alert` com o orquestrador
- Startup da API reconcilia workflows via [`../market_alert/main.py`](../market_alert/main.py) (`WorkflowReconciler().reconcile_all()`).
- Worker Celery inicia o Temporal Worker em thread daemon no `worker_ready` via [`../market_alert/infraestructure/worker_lifecycle.py`](../market_alert/infraestructure/worker_lifecycle.py).
- Health check consulta conectividade Temporal com `probe_connectivity_sync()` em [`../market_alert/infraestructure/routes/routes_health.py`](../market_alert/infraestructure/routes/routes_health.py).
- Lifecycle de monitorados usa os métodos de facade `start_monitoring`, `pause_monitoring`, `resume_monitoring`, `delete_monitoring` em [`../market_alert/products/services/services_monitored_lifecycle.py`](../market_alert/products/services/services_monitored_lifecycle.py).
- Lifecycle de concorrentes usa `notify_competitor_changed` em [`../market_alert/products/services/services_competitor_lifecycle.py`](../market_alert/products/services/services_competitor_lifecycle.py).
- Endpoint `GET /monitored/{product_id}/workflow-status` consulta `query_sync()` em [`../market_alert/products/routes/routes_monitored.py`](../market_alert/products/routes/routes_monitored.py).
- Tarefa periodica de reconciliação (`reconcile-workflows-periodic`, 600s / 10 min) em [`../market_alert/infraestructure/celery/config.py`](../market_alert/infraestructure/celery/config.py) chama [`../market_alert/infraestructure/tasks/reconciler_task.py`](../market_alert/infraestructure/tasks/reconciler_task.py).
- Endpoint `GET /health/temporal` em [`../market_alert/infraestructure/routes/routes_health.py`](../market_alert/infraestructure/routes/routes_health.py) retorna `{ status, temporal_connected, namespace, task_queue, last_check_at }` via `probe_connectivity_sync()`. HTTP 200 quando conectado (`status=healthy`), HTTP 503 quando indisponível (`status=unhealthy`). Nunca propaga exceção — falha é reportada no body com `error`.

### Relação com `market_scraper`
`market_orchestrator` não conversa diretamente com `market_scraper`. O caminho e indireto:
1. Workflow chama `dispatch_collection`.
2. Activity enfileira no fluxo Celery de `market_alert`.
3. Task de coleta do `market_alert` chama o cliente HTTP do `market_scraper`.

---

## Fluxo de Trabalho

### 1. Criação de monitorado
1. `market_alert` cria monitorado e enfileira coleta imediata.
2. `market_alert` chama `signal_with_start_sync(WorkflowInput)` no cliente Temporal.
3. Workflow inicia em `WaitingTimer` e passa a governar os ciclos seguintes.

### 2. Ciclo continuo de monitoramento
1. `WaitingTimer` lê policy atual (`fetch_monitored_policy`) e aguarda `next_check_at`.
2. `Dispatching` gera `correlation_id/trace_id` e enfileira coleta (`dispatch_collection`).
3. `WaitingResult` faz polling de conclusão (`query_collection_status`) com timeout.
4. Em sucesso, volta para `WaitingTimer`; em timeout/falha, vai para `Backoff`.
5. Em limite de tentativas, finaliza em `FailedTerminal`.

### 3. Eventos de ciclo de vida
- **Pausar**: signal `pause` move para `Paused`.
- **Retomar**: signal `resume` pode retomar com ou sem coleta imediata.
- **Deletar**: signal `delete` executa `cleanup_workflow_state` e encerra.
- **Mudanca de concorrente**: signal `competitor_changed` pode preemptar timer e antecipar ciclo.

### 4. Reconciliação
`WorkflowReconciler` lista monitorados ativos no banco e, para cada um:
1. Consulta `query_sync(monitored_id)`.
2. Se workflow não existir, inicia com `signal_with_start_sync`.
3. Retorna contadores operacionais (`total`, `started`, `alive`, `errors`).

---

## Configuração
As configurações do módulo estão em [`core/config_orchestrator.py`](core/config_orchestrator.py), carregadas por `OrchestratorSettings`.

### Ordem de carregamento
1. Defaults definidos em codigo.
2. Fora de teste, `.env.market_orchestrator` sobrescreve defaults quando presente.
3. Variáveis exportadas no ambiente do processo tem precedencia final.
4. Em teste (`PYTEST_RUNNING=1`), nenhum `.env` e carregado pelo modulo; a suite usa apenas defaults Python e overrides declarados em `tests/conftest.py`.

> **Importante — Docker:** o `env_file` usa caminho relativo e pode não ser encontrado dependendo do working directory do container. Em ambiente Docker, declare `TEMPORAL_HOST` e `TEMPORAL_PORT` diretamente no ambiente do processo. A forma canônica é adicioná-los em `.env.common` (carregado por todos os serviços via docker-compose). Variáveis de processo sempre têm precedência sobre o `env_file`.
>
> Linha obrigatória em `.env.common` para ambiente Docker:
> ```env
> TEMPORAL_HOST=temporal
> TEMPORAL_PORT=7233
> ```

### Categorias de variaveis
| Categoria | Variaveis relevantes |
|-----------|----------------------|
| Temporal | `TEMPORAL_HOST`, `TEMPORAL_PORT`, `TEMPORAL_NAMESPACE`, `TEMPORAL_TASK_QUEUE` |
| Limites de historico/signal | `WORKFLOW_HISTORY_LENGTH_LIMIT`, `WORKFLOW_SIGNAL_COUNT_LIMIT` |
| Polling de resultado | `COLLECTION_RESULT_TIMEOUT_SECONDS`, `COLLECTION_POLL_INTERVAL_SECONDS` |
| Retry de activity | `RETRY_MAX_ATTEMPTS`, `RETRY_INITIAL_INTERVAL_SECONDS`, `RETRY_MAX_INTERVAL_SECONDS`, `RETRY_BACKOFF_COEFFICIENT` |
| Timeouts de activities | `ACTIVITY_DISPATCH_TIMEOUT_SECONDS`, `ACTIVITY_QUERY_STATUS_TIMEOUT_SECONDS`, `ACTIVITY_PERSIST_SNAPSHOT_TIMEOUT_SECONDS`, `ACTIVITY_CLEANUP_TIMEOUT_SECONDS`, `ACTIVITY_FETCH_POLICY_TIMEOUT_SECONDS` |
| Snapshot Redis | `SNAPSHOT_KEY_TEMPLATE`, `SNAPSHOT_TTL_SECONDS` |
| Infra Temporal DB (compose) | `TEMPORAL_DB_HOST`, `TEMPORAL_DB_PORT`, `TEMPORAL_DB_USER`, `TEMPORAL_DB_PASSWORD`, `TEMPORAL_DB_NAME`, `TEMPORAL_DATABASE_URL` |

Exemplo minimo de `.env.market_orchestrator`:
```env
TEMPORAL_HOST=temporal
TEMPORAL_PORT=7233
TEMPORAL_NAMESPACE=default
TEMPORAL_TASK_QUEUE=market-orchestrator

WORKFLOW_HISTORY_LENGTH_LIMIT=5000
WORKFLOW_SIGNAL_COUNT_LIMIT=500

COLLECTION_RESULT_TIMEOUT_SECONDS=1800
COLLECTION_POLL_INTERVAL_SECONDS=30

RETRY_MAX_ATTEMPTS=5
RETRY_INITIAL_INTERVAL_SECONDS=10
RETRY_MAX_INTERVAL_SECONDS=300
RETRY_BACKOFF_COEFFICIENT=2.0

ACTIVITY_DISPATCH_TIMEOUT_SECONDS=30
ACTIVITY_QUERY_STATUS_TIMEOUT_SECONDS=15
ACTIVITY_PERSIST_SNAPSHOT_TIMEOUT_SECONDS=10
ACTIVITY_CLEANUP_TIMEOUT_SECONDS=10
ACTIVITY_FETCH_POLICY_TIMEOUT_SECONDS=15

SNAPSHOT_KEY_TEMPLATE=workflow:snapshot:{monitored_id}
SNAPSHOT_TTL_SECONDS=86400
```

---

## Suite de Testes

### Estrutura da suite
```text
market_orchestrator/tests/
|-- conftest.py                 # defaults de ambiente, reload de settings, paths e markers
|-- unit/
|   |-- conftest.py             # fixtures locais do workflow e helpers fakes
|   |-- test_workflow_core.py
|   |-- test_workflow_signals.py
|   |-- test_workflow_contracts.py
|   |-- test_dispatch_activity.py
|   |-- test_status_activity.py
|   |-- test_policy_activity.py
|   `-- test_snapshot_activity.py
`-- integration/
    |-- conftest.py             # WorkflowEnvironment, fixtures de ids e inputs
    |-- test_worker_bootstrap.py
    `-- test_temporal_integration.py
```

### Marcacoes e convencoes
- `@pytest.mark.unit`: testes isolados sem I/O real, sem banco real, sem Redis real e sem servidor Temporal.
- `@pytest.mark.integration`: testes de contrato e fluxo com infraestrutura controlada.
- `@pytest.mark.integration_high_cost`: subconjunto que sobe `temporal-test-server` do SDK e por isso deve ficar fora da execucao rapida padrao.
- Arquivos seguem `test_<area>.py`; fixtures compartilhadas ficam em `conftest.py`; casos locais do modulo ficam abaixo de `tests/unit` e `tests/integration`.

### Fixtures e decisoes de isolamento
- `tests/conftest.py` centraliza `orchestrator_test_env_defaults`, `env_override`, `reload_orchestrator_modules` e `fresh_orchestrator_settings` para manter config previsivel entre testes.
- A suite nao usa `.env.test` nem `ENV_FILE` dedicado. O bootstrap de teste e controlado apenas por `PYTEST_RUNNING=1`, com defaults locais em Python.
- `tests/unit/conftest.py` concentra `workflow_instance`, `workflow_policy`, IDs validos e helpers para fakes de sessao/row.
- Unit usa monkeypatch e doubles para `workflow.execute_activity`, `SessionLocal`, Redis e dispatcher Celery.
- Integration usa `temporalio.testing.WorkflowEnvironment.start_time_skipping()` para validar worker, workflow e client sem depender de Temporal externo do projeto.
- O boundary do Temporal serializa payloads de activity/query como `dict` em alguns caminhos; o workflow e o client normalizam esses retornos explicitamente para manter o contrato tipado.

### Comandos recomendados
- Configuracao canônica do `pytest`: `backend/pytest.ini` unico para todo o backend. Nao existe `pytest.ini` local por modulo.
- Suite unit do modulo: `.\.venv\Scripts\python.exe -m pytest -c backend/pytest.ini backend/market_orchestrator/tests/unit -q`
- Suite de integracao do modulo: `.\.venv\Scripts\python.exe -m pytest -c backend/pytest.ini backend/market_orchestrator/tests/integration -q`
- Execucao completa do modulo sem cenarios caros: `.\.venv\Scripts\python.exe -m pytest -c backend/pytest.ini backend/market_orchestrator/tests -m "not integration_high_cost" -q`
- Execucao do subconjunto caro de Temporal: `.\.venv\Scripts\python.exe -m pytest -c backend/pytest.ini backend/market_orchestrator/tests -m integration_high_cost -q`
- Cobertura do modulo: `.\.venv\Scripts\python.exe -m pytest -c backend/pytest.ini backend/market_orchestrator/tests --cov=market_orchestrator --cov-report=term -q`

### Observacoes operacionais
- A descoberta oficial do backend fica em [`../pytest.ini`](../pytest.ini) e inclui explicitamente `market_orchestrator/tests`.
- O `pytest.ini` fixa `asyncio_default_fixture_loop_scope=function` para evitar comportamento implicito diferente entre versoes do `pytest-asyncio`.
- Na primeira execucao dos testes de integracao com `WorkflowEnvironment`, o SDK pode precisar baixar o `temporal-test-server` se ele ainda nao estiver em cache local.

---

## Operação e Execução

### Infra Temporal no docker-compose
O compose possui perfil `temporal` com servicos dedicados:
- `temporal-db` (PostgreSQL do Temporal)
- `temporal` (`temporalio/auto-setup`)
- `temporal-ui` (`temporalio/ui`, porta `8088`)

As definicoes operacionais ativas estao em [`../../docker-compose.base.yml`](../../docker-compose.base.yml), [`../../docker-compose.dev.yml`](../../docker-compose.dev.yml) e [`../../docker-compose.hml.yml`](../../docker-compose.hml.yml).

---

## Confiabilidade e Observabilidade
- **Determinismo do workflow**: I/O fica fora do workflow, todo acesso externo passa por activities.
- **Fallback não bloqueante**: cliente do Temporal retorna `False/None` em falha para não derrubar fluxo de negocio.
- **Snapshots best-effort**: estado operacional e salvo no Redis sem impactar o ciclo se houver falha.
- **Reconciliação periodica**: reduz risco de monitorado ativo sem workflow (a cada 10 minutos via Celery Beat).
- **Logs estruturados**: `structlog` em workflow, worker, activities, reconciler e client. O processor `_inject_trace_id` em `shared/infra/logging.py` injeta automaticamente `trace_id` do `ContextVar` em todos os eventos de log; `dispatch_collection` seta o ContextVar para propagar o trace_id gerado pelo workflow para os logs de activities e tasks Celery.
- **Correlação de dispatch**: `dispatch_collection` salva o timestamp de dispatch no Redis (`workflow:dispatch:{monitored_id}:{correlation_id}`, TTL 2h); `query_collection_status` compara `last_collected_at >= dispatch_timestamp` para garantir que apenas coletas posteriores ao dispatch corrente contam como conclusão.

## Pontos de Atenção Atuais
- No setup atual, o Temporal Worker roda co-localizado com worker Celery (thread daemon em `worker_ready`), o que simplifica operação mas compartilha recursos do processo.
- O módulo não possui API HTTP propria; todo acesso operacional acontece via cliente em `market_alert`.
- Se o Redis estiver indisponível no momento do `query_collection_status`, o fallback aceita qualquer `last_collected_at` para evitar loop infinito de polling.

---

## Fronteiras de Domínio

### Matriz de Responsabilidade

| Módulo | Pode depender de | NÃO pode depender de |
|--------|-----------------|----------------------|
| `market_orchestrator` | `shared` (contratos, infra, utils) | `market_alert` (acoplamento proibido); `market_scraper` |
| `market_alert` | `shared` | internals de `market_orchestrator` fora de adaptador |
| `market_scraper` | `shared` | `market_alert`; `market_orchestrator` |
| `shared` | bibliotecas externas | qualquer serviço específico |

### Regras Obrigatórias

- **`market_orchestrator` NÃO importa `market_alert`** — esta é a regra mais crítica do domínio. Toda integração com lógica de negócio é feita via contrato neutro ou injeção.
- **Activities acessam banco via SQL direto** (`sqlalchemy.text`) sem importar modelos ORM de `market_alert`.
- **Enqueue de coleta** deve ser feito via interface injetável neutra, não via import direto de `market_alert.collectors`.
- **`shared` não importa nenhum serviço específico** — é infraestrutura neutra.

### Estado Atual de Acoplamentos Documentados

| Arquivo | Acoplamento existente | Ação necessária |
|---------|-----------------------|----------------|
| ~~`activities/dispatch_activity.py:82`~~ | ~~`from market_alert...enqueue_collect`~~ | **Resolvido** — usa `shared.clients.celery.task_dispatcher.send_collection_task` |

---

> Nota final: mantenha este README sincronizado com qualquer mudanca em estados do workflow, signals, activities, contratos de dataclasses, variaveis de ambiente e fluxo de integração com `market_alert`.
