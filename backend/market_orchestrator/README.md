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
- **Reconciliar monitorados ativos com workflows vivos** para reduzir gaps apos restart/falhas.
- **Fornecer cliente adaptador para o dominio** (`TemporalOrchestrationClient`) com wrappers sincronos e fallback não bloqueante.

## Estrutura do Diretório
```text
market_orchestrator/
|-- activities/                 # Activities de I/O (bridge Temporal <-> dominio)
|   |-- dispatch_activity.py    # Enfileira coleta no market_alert
|   |-- status_activity.py      # Consulta status de coleta no banco de negocio
|   |-- snapshot_activity.py    # Persiste/limpa snapshot no Redis
|   |-- policy_activity.py      # Le politica atual do monitorado
|   `-- __init__.py             # Exporta activities para registro no worker
|-- alert/
|   `-- alert_client.py         # TemporalOrchestrationClient + singleton
|-- core/
|   `-- config_orchestrator.py  # OrchestratorSettings e variaveis de ambiente
|-- enums/
|   `-- enums_workflow.py       # WorkflowState
|-- schemas/                    # Dataclasses de input/signals/snapshot/policy
|-- workflow.py                 # MonitoredProductWorkflow (deterministico)
|-- worker.py                   # Bootstrap do Temporal Worker
|-- reconciler.py               # WorkflowReconciler para convergencia
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
- [`reconciler.py`](reconciler.py): garante workflow para todo monitorado ativo (`paused=False`).
- [`alert/alert_client.py`](alert/alert_client.py): API de consumo para `market_alert` (start/signal/query/probe).
- [`core/config_orchestrator.py`](core/config_orchestrator.py): configuração central e validações de ambiente.

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
| Activity | Funcao | Integração principal |
|----------|--------|----------------------|
| `dispatch_collection` | Enfileira coleta do monitorado | `market_alert.collectors.orchestrator.enqueue_collect` |
| `query_collection_status` | Infere conclusão da coleta | leitura de `MonitoredProduct.last_collected_at` |
| `fetch_monitored_policy` | Lê policy atual do monitorado | leitura de `check_interval`, `next_check_at`, `paused` |
| `persist_workflow_snapshot` | Salva snapshot de estado no Redis | chave `workflow:snapshot:{monitored_id}` |
| `cleanup_workflow_state` | Remove estado transitario | delete da chave de snapshot |

---

## Integração com Market Alert e Market Scraper

### Integrações do `market_alert` com o orquestrador
- Startup da API reconcilia workflows via [`../market_alert/main.py`](../market_alert/main.py) (`WorkflowReconciler().reconcile_all()`).
- Worker Celery inicia o Temporal Worker em thread daemon no `worker_ready` via [`../market_alert/infraestructure/worker_lifecycle.py`](../market_alert/infraestructure/worker_lifecycle.py).
- Health check consulta conectividade Temporal com `probe_connectivity_sync()` em [`../market_alert/infraestructure/routes/routes_health.py`](../market_alert/infraestructure/routes/routes_health.py).
- Lifecycle de monitorados usa `signal_with_start_sync` e `signal_sync` em [`../market_alert/products/services/services_monitored_lifecycle.py`](../market_alert/products/services/services_monitored_lifecycle.py).
- Lifecycle de concorrentes sinaliza `competitor_changed` em [`../market_alert/products/services/services_competitor_lifecycle.py`](../market_alert/products/services/services_competitor_lifecycle.py).
- Endpoint `GET /monitored/{product_id}/workflow-status` consulta `query_sync()` em [`../market_alert/products/routes/routes_monitored.py`](../market_alert/products/routes/routes_monitored.py).
- Tarefa periodica de reconciliação (`reconcile-workflows-periodic`, 600s) em [`../market_alert/infraestructure/celery/config.py`](../market_alert/infraestructure/celery/config.py) chama [`../market_alert/infraestructure/tasks/reconciler_task.py`](../market_alert/infraestructure/tasks/reconciler_task.py).

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
As configurações do módulo estão em [`core/config_orchestrator.py`](core/config_orchestrator.py), carregadas por `OrchestratorSettings` com `env_file=.env.market_orchestrator`.

### Ordem de carregamento
1. Defaults definidos em codigo.
2. `.env.market_orchestrator` sobrescreve defaults quando presente.
3. Variáveis exportadas no ambiente do processo tem precedencia final.

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

RETRY_MAX_ATTEMPTS=3
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

## Operação e Execução

### Infra Temporal no docker-compose
O compose possui perfil `temporal` com servicos dedicados:
- `temporal-db` (PostgreSQL do Temporal)
- `temporal` (`temporalio/auto-setup`)
- `temporal-ui` (`temporalio/ui`, porta `8088`)

As definicoes estao em [`../../docker-compose.yml`](../../docker-compose.yml).

---

## Confiabilidade e Observabilidade
- **Determinismo do workflow**: I/O fica fora do workflow, todo acesso externo passa por activities.
- **Fallback não bloqueante**: cliente do Temporal retorna `False/None` em falha para não derrubar fluxo de negocio.
- **Snapshots best-effort**: estado operacional e salvo no Redis sem impactar o ciclo se houver falha.
- **Reconciliação periodica**: reduz risco de monitorado ativo sem workflow.
- **Logs estruturados**: `structlog` em workflow, worker, activities, reconciler e client.

## Pontos de Atenção Atuais
- O `query_collection_status` usa `last_collected_at` como proxy de conclusão (não correlaciona explicitamente por `correlation_id`).
- No setup atual, o Temporal Worker roda co-localizado com worker Celery (thread daemon em `worker_ready`), o que simplifica operação mas compartilha recursos do processo.
- O módulo não possui API HTTP propria; todo acesso operacional acontece via cliente em `market_alert`.

---

> Nota final: mantenha este README sincronizado com qualquer mudanca em estados do workflow, signals, activities, contratos de dataclasses, variaveis de ambiente e fluxo de integração com `market_alert`.
