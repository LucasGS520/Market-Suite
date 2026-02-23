# Plano de Refatoração - Orquestração de Coletas

## Análise de Riscos e Decisões Chave
Adotar um padrão de Orquestrador Centralizado (`CollectionOrchestrator`) que:
- Valida payloads contra schema explícito antes de enfileirar.
- Gerencia retries via uma política única (`RetryPolicy`).
- Encapsula `PriorityQueueService` e expõe apenas operações de domínio (enfileirar para coleta, remover, reenfileirar).
- Integra callbacks Celery (link=, link_error=) de forma clara.

* Risco Principal: Mudanças no contrato de payload podem quebrar tasks em fila que ainda esperam formato antigo.
* Mitigação: Versionamento de payload (version=1), validação com fallback, logging de incompatibilidade. Executar reconciliação da fila após deploy.

* **Dependências:**
- Celery (para callbacks link= / link_error=).
- Redis (Lua scripts, operações atômicas).
- SQLAlchemy ORM (iteração de monitorados para reconciliação).
- structlog (rastreamento distribuído com trace_id).

---

## Plano de Implementação

### Fase 1 — Padronização de Contrato (Payload)
Cria um modelo explícito para o payload, substituindo dicts soltos por Pydantic

- [] **Schema:** Criar `schemas/schemas_collection_payload.py` com:
  - CollectionPayload (Pydantic) com campos obrigatórios: `kind`, `monitored_id`, `url`, `trace_id`, `version`.
  - Campos opcionais: `competitor_id`, `user_id`, `enqueued_at`, `force_compare`, `collected_at`.
  - Função `validate_payload(payload: dict) -> CollectionPayload` que retorna erro descritivo se inválido.
  - Documentação clara do versionamento (como lidar com futuras mudanças).

- [] **Migração de Builders:** Atualizar builders em `orchestrator/collector_service_orchestrator.py`:
  - `build_monitored_payload()` → retorna CollectionPayload estruturado, não dict.
  - `build_competitor_payload()` → retorna CollectionPayload estruturado.
  - Ambos garantem `version=1` e `trace_id` sempre preenchido (gera UUID se None).

- [] **Remoção de Builders Duplicados:** Deletar `_merge_competitor_payload()` de `scraper_tasks.py`, reutilizar o builder centralizado.

- [] **Validação Centralizada:** Importar `validate_payload()` em `collector_product_task.py` e validar no início da tarefa, antes de qualquer lógica.

---

### Fase 2 — Consolidação de Portas de Entrada
Unifica `enqueue_collect` (orchestrator) e `_dispatch_collect_task` (continuous_dispatch) em um único ponto.

- [] **Novo Módulo:** Criar `orchestrator/collection_enqueuer.py` com:
  - Classe `CollectionEnqueuer`:
    - Método `enqueue_monitored(monitored: MonitoredProduct, user_id: UUID, trace_id: str | None = None) -> str` → retorna `trace_id` usado.
    - Método `enqueue_competitor(competitor: CompetitorProduct, user_id: UUID | None = None, countdown: float | None = None, trace_id: str | None = None) -> str`.
    - Método `enqueue_group(monitored, competitors: list, user_id: UUID) -> dict[str, str]` → retorna mapa de IDs para trace_ids.
    - Todas as funções constroem payload via builders centralizados, validam, e chamam `_enqueue_to_celery()` internamente.
    - Logging consistente de tentativa de enfileiramento (trace_id, monitored_id, competitor_id, countdown).
  
- [] **Remover Duplicação:** Deletar `enqueue_collect()` e `_dispatch_collect_task()`, substituir usos por `CollectionEnqueuer`.
  
- [] **Atualizar Imports:** Em `continuous_dispatch.py`, `services_monitored_lifecycle.py`, `services_competitor_lifecycle.py`:
  - Remover imports diretos de `enqueue_collect` / `_dispatch_collect_task`.
  - Importar e usar `CollectionEnqueuer` em vez disso.

- [] **Atualizar `scraper_task.py`:** Usar `CollectionEnqueuer.enqueue_group()` ou `enqueue_competitor()` em vez de montar payload manualmente.

---

### Fase 3 — Abstração da Fila Redis (PriorityQueueService)
Encapsula `PriorityQueueService` atrás de uma interface orientada ao domínio de coleta.

- [] **Nova Interface:** Criar `orchestrator/collection_queue.py` com:
  - Classe `CollectionQueue` (wrapper de `PriorityQueueService`):
    * Métodos públicos (orientados ao domínio):
      - `enqueue_for_collection(monitored_id: UUID, scheduled_at: datetime) -> bool` — enfileira para coleta contínua.
      - `pop_next_for_collection(now: datetime | None = None) -> tuple[str, datetime] | None` — remove próximo item pronto.
      - `mark_processing(monitored_id: str) -> bool` — marca como em processamento (move para processing_key).
      - `reenqueue_after_collection(monitored_id: UUID, next_check_at: datetime) -> bool` — reenfileira após coleta encerrada.
      - `remove_from_collection(monitored_id: UUID) -> bool` — remove (monitorado pausado/deletado).
      - `reclaim_stale_items(stale_after_seconds: int) -> list[str]` — recupera itens travados.
      - `get_collection_status(monitored_id: UUID) -> str` — retorna "queued", "processing", "not_found".
    * Métodos privados delegam para `PriorityQueueService` internamente.
    * Logging estruturado em cada operação crítica (enqueue, pop, requeue, reclaim).

- [] **Remover Imports Diretos:** Em `continuous_dispatch.py`, `continuous_collector_task.py`, `priority_queue_tasks.py`:
  - Substituir `from market_alert.services.services_priority_queue import PriorityQueueService` por `from market_alert.orchestrator.collection_queue import CollectionQueue`.
  - Atualizar todas as chamadas para usar métodos públicos de `CollectionQueue`.

- [] **Manter PriorityQueueService Internamente:** `PriorityQueueService` continua como está (implementação de Redis), mas deixa de ser importado externamente.

---

### Fase 4 — Centralização de Decisões de Retry
Consolida lógica de retry espalhada em `collector_product_task.py`, `continuous_dispatch.py`, `interval_calculator_products.py`.

- [] **Novo Módulo:** Criar `orchestrator/retry_policy.py` com:
  - Classe `RetryPolicy`:
  * Métodos estáticos:
    - `should_retry_lock_failure(attempt: int, max_attempts: int = 3) -> tuple[bool, float]` — (deve_retry, delay_seconds).
    - `should_retry_scrape_failure(reason: str, attempt: int) -> tuple[bool, datetime | None]` — (deve_retry, next_check_at).
    - `compute_lock_retry_delay(attempt: int) -> float` — backoff vinculado do attempt.
    - `compute_scrape_retry_delay(reason: str, attempt: int, base_cooldown: int = 60) -> float` — delay por tipo de erro.
  * Constantes centralizadas:
    - `LOCK_RETRY_MAX_RETRIES = 3`
    - `LOCK_RETRY_MAX_DELAY_SECONDS = 30`
    - `SCRAPE_RETRY_MAX_ATTEMPTS = 5`
    - `SCRAPE_RETRY_WINDOW_SECONDS = 15 * 60`
    - `COOLDOWN_REASONS = {"rate_limit", "429", "temporary_failure"}`
  * Documentação clara de cada política (quando aplicar, por que, exemplo de fluxo).

- [] **Integração com Interval Calculator:** Atualizar `interval_calculator_products.py`:
  - `calculate_schedule()` agora recebe `retry_policy: RetryPolicy | None = None` como parâmetro.
  - Se `retry_policy` fornecido, usa `RetryPolicy.should_retry_scrape_failure()` para calcular `next_check_at`.
  - Se não fornecido, usa lógica padrão de estabilidade (atual).

- [] **Atualizar Collector Task:** Em `collector_product_task.py`:
  - Deletar constantes `LOCK_RETRY_MAX_RETRIES`, `SCRAPE_RETRY_MAX_SECONDS`, etc.
  - Importar `RetryPolicy`.
  - Usar `RetryPolicy.should_retry_lock_failure()` no loop de lock.
  - Usar `RetryPolicy.should_retry_scrape_failure()` ao decidir se reenfileira.
  - Usar `RetryPolicy.compute_lock_retry_delay()` em vez de `_compute_lock_retry_delay()`.

- [] **Atualizar Continuous Dispatch:**  Em `continuous_dispatch.py`:
  - `_dispatch_collect_task()` agora recebe `retry_policy: RetryPolicy` como parâmetro (não usa mais nomes mágicos).
  - `_handle_processing_requeue()` usa `RetryPolicy.should_retry_scrape_failure()` para decidir próximo check.

---

### Fase 5 — Sincronização e Callbacks
Padroniza finalizações, callbacks Celery e reconciliação de fila.

#### Fase 5.1 - Padronização de Callbacks Celery

- [] **Novo Módulo:** Criar `orchestrator/collection_callbacks.py` com:
  - Classe `CollectionCallbacks`:
  * Método estático `on_collection_success(collect_result: dict, monitored_id: str, trace_id: str | None) -> None`:
    - Parse de resultado.
    - Reenfileiramento na fila (via CollectionQueue).
    - Drenagem de processing set.
    - Enfileiramento de comparação desacoplado (vide 5.2).
    - Logging de sucesso e próximo check.
  * Método estático `on_collection_error(exception: Exception, monitored_id: str, trace_id: str | None) -> None`:
    - Reenfileiramento com backoff (via `RetryPolicy`).
    - Drenagem de processing set.
    - Logging de erro e ação tomada.
* (Esses métodos são invocados pelos callbacks Celery `link=` e `link_error=.`)

- [] **Integração em `continuous_collector_task.py`:**
  -  Deletar `finalize_processing_requeue()` e `finalize_processing_requeue_error()` (tasks Celery).
  - Integrar callbacks diretamente no `run_continuous_collector()`:
    - Ao receber resultado de `_collect_group()`, invocar `CollectionCallbacks.on_collection_success()`.
    - Capturar exceções e invocar `CollectionCallbacks.on_collection_error()`.

- [] **Documentação de Callbacks:** Explicar no cabeçalho do módulo:
  - Como Celery `link=` funciona.
  - Por que não há "link_error" automático (tasks de erro devem ser explícitas no loop).
  - Fluxo esperado: task → sucesso → callback → reenfileira OR task → erro → tratamento inline.

#### Fase 5.2 — Desacoplamento da Comparação

- [] **Novo Helper:** Criar função em novo módulo `orchestrator/collection_triggers.py`:
  - `trigger_comparison_if_needed(monitored_id: UUID, payload: CollectionPayload, collect_result: dict) -> bool`:
    - Le `force_compare` do payload.
    - Se não há preço no resultado, não enfileira comparação.
    - Enfileira task de comparação via CeleryApp.send_task() direto, não via orchestrador de coleta.
    - Retorna `True` se enfileirou, `False` caso contrário.
  - Importar em `collector_product_task.py` (lugar atual).
  - Comentário claro: "Comparação é responsabilidade separada, disparada após coleta bem-sucedida."

- [] **Remover Import Direto:** Remover import de `price_comparator` de `collector_product_task.py`, substituir por `trigger_comparison_if_needed()`.

#### Fase 5.3 - Sincronização de Reconciliação

- [] **Novo Módulo:** Criar `orchestrator/collection_reconciliation.py` com:
  - Função `reconcile_collection_queue(collection_queue: CollectionQueue) -> dict[str, int]`:
    - Itera monitorados ativos via `_iter_active_monitored()`.
    - Para cada um, verifica estado em `collection_queue.get_collection_status()`.
    - Se `not_found` e `next_check_at <= now`, enfileira via `collection_queue.enqueue_for_collection()`.
    - Se `processing` e estale (últimos N segundos sem atualização), invoca `collection_queue.reclaim_stale_items()`.
    - Retorna estatísticas: total, enfileirados, reclamados.
  - Documentação clara: quando rodar, por quê (segurança contra perda de items no processamento).
 
- [] **Atualizar `priority_queue_tasks.py`:**
  - Deletar implementação atual de `reconcile_priority_queue()`.
  - Chamar `reconcile_collection_queue()`

- [] **Sincronização de Racecondition:**
  - Adicionar flag Redis: `market_alert:collection:reconciliation:running` (TTL: tempo máximo de reconciliação).
  - Antes de iniciar reconciliação, verificar se a flag está set; se sim, aguardar ou pular.
  - Documentação: "Reconciliação e loop contínuo são tolerantes a sobreposição porque operações Redis são atômicas (Lua scripts)."

---

### Fase 6 — Consolidação de Imports e Limpeza
Remove imports espalhados e padroniza pontos de entrada

- [] **Atualizar services/services_monitored_lifecycle.py:**
  - Deletar imports de `build_monitored_payload`, `enqueue_collect`.
  - Importar `CollectionEnqueuer` de `orchestrator.collection_enqueuer`.
  - Atualizar todas as chamadas para usar `CollectionEnqueuer`.
  * Exemplo: `enqueue_collect()` → `CollectionEnqueuer().enqueue_monitored()`.
 
- [] **Atualizar services/services_competitor_lifecycle.py:**
  - Deletar imports de `enqueue_competitor_collection`.
  - Importar `CollectionEnqueuer`.
  - Atualizar chamadas: `enqueue_competitor_collection()` → `CollectionEnqueuer().enqueue_competitor()`.

- [] **Atualizar utils/continuous_dispatch.py:**
  - Deletar imports de `PriorityQueueService` direto.
  - Importar `CollectionQueue`, `RetryPolicy`, `CollectionCallbacks`, `trigger_comparison_if_needed`.
  - Remover `_dispatch_collect_task()`, usar `CollectionEnqueuer().enqueue_group()` internamente.
  - Remover `_handle_processing_requeue()`, usar `CollectionCallbacks.on_collection_success/error()`.

- [] **Atualizar tasks/continuous_collector_task.py:**
  - Importar `CollectionQueue`, `RetryPolicy`, `CollectionCallbacks`.
  - Deletar `_drain_processing()`, usar `CollectionQueue.mark_processing()` / drenagem interna.
  - Deletar `finalize_processing_requeue*()` tasks.
  - Loop principal invoca `CollectionCallbacks` em vez de `_handle_processing_requeue()`.

- [] **Atualizar tasks/collector_product_task.py:**
  - Deletar imports de constantes de retry.
  - Importar `RetryPolicy`, `CollectionPayload`, `validate_payload()`, `trigger_comparison_if_needed()`.
  - Usar `RetryPolicy` para decisões de retry.
  - Validar payload no início da função.

- [] **Deletar em scraper_tasks.py:**
  - Deletar completamente (se ninguém mais usa).

- [] **Exportar públicos de `orchestrator/init.py`:**
  - Adicionar ao __all__:
  ```
  from .collection_enqueuer import CollectionEnqueuerfrom .collection_queue import CollectionQueuefrom .retry_policy import RetryPolicyfrom .collection_callbacks import CollectionCallbacksfrom .collection_triggers import trigger_comparison_if_neededfrom .collection_reconciliation import reconcile_collection_queue
  ```
---

## Definição de Pronto (Definition of Done)

O trabalho de refatoração está **completo** quando:

- [] **Contrato de Payload:** Schema `CollectionPayload` definido, validado em ponto único, documentado.
- [] **Porta de Entrada Única:** `CollectionEnqueuer` é o único lugar que chama `current_app.send_task()` para coleta.
- [] **Fila Abstraída:** `PriorityQueueService` nunca é importado fora de orchestrator/collection_queue.py.
- [] **Retry Centralizado:** `RetryPolicy` é consultado em todas as decisões de retry.
- [] **Callbacks Padronizados:** Não há lógica de reenfileiramento espalhada; tudo passa por `CollectionCallbacks`.
- [] **Sem Acoplamento Coleta-Comparação:** `collector_product_task.py` chama `trigger_comparison_if_needed()` apenas, sem conhecer detalhes de comparação.
- [] **Atualização de Documentação:**
  - Cabeçalhos de módulos explicam responsabilidade única e fluxo esperado.
  - Arquivo `CLAUDE.md` atualizado com nova arquitetura de orquestração.
  - Diagrama de fluxo (Mermaid ou texto) mostrando: Enqueue → Pop → Collect → Callback → Reenqueue.

---

> Este plano elimina os diversos blocos de problemas identificados, fornecendo um caminho claro para restaurar a arquitetura limpa do módulo `market_alert`.
