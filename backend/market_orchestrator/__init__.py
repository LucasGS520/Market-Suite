"""
market_orchestrator — Orquestração Contínua com Temporal

Módulo responsável pelo plano de controle durável de cada monitoramento ativo.
Cada monitorado ativo é uma Workflow Execution independente e persistente.

Componentes:
  - workflow.py        — MonitoredProductWorkflow (máquina de estados)
  - activities.py      — Activities de integração (ponte Temporal ↔ Celery/DB/Redis)
  - worker.py          — Temporal Worker Python
  - reconciler.py      — Reconciliador de monitorados ativos
  - alert/alert_client — TemporalOrchestrationClient (adaptador para o domínio)
  - schemas/           — Dataclasses de input/output/signals/queries
  - core/              — Configurações (OrchestratorSettings)

A camada de execução existente não foi alterada:
  - Celery workers e tasks (market_alert/tasks/)
  - CollectionEnqueuer (market_alert/infraestructure/celery/enqueuer.py)
  - payload_builders (market_alert/collectors/orchestrator/payload_builders.py)
"""
from market_orchestrator.alert.alert_client import TemporalOrchestrationClient, get_temporal_client
from market_orchestrator.schemas.schemas_workflow import (
    CollectionPolicy,
    CompetitorChangedPayload,
    ResumeSignalPayload,
    UpdatePolicySignalPayload,
    WorkflowInput,
    WorkflowSnapshot,
    WorkflowState,
)

__all__ = [
    "TemporalOrchestrationClient",
    "get_temporal_client",
    "WorkflowInput",
    "WorkflowState",
    "WorkflowSnapshot",
    "CollectionPolicy",
    "ResumeSignalPayload",
    "UpdatePolicySignalPayload",
    "CompetitorChangedPayload",
]
