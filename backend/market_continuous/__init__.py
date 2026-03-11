"""
market_continuous — Orquestração Contínua

Módulo em reestruturação. A orquestração baseada em Redis foi removida.
Próxima fase: implementação de orquestração com Temporal.

O que foi removido:
  - orchestrator/ (manager, dispatcher, callbacks, reconciliation)
  - services/services_priority_queue.py (Redis Sorted Set)
  - queue/collection_queue.py (interface da fila)
  - main.py (entrada do processo standalone)

O que permanece operacional:
  - Celery workers e tasks (market_alert/tasks/)
  - CollectionEnqueuer (market_alert/infra/celery/enqueuer.py)
  - payload_builders (market_alert/collectors/orchestrator/payload_builders.py)
"""
