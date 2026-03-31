"""
market_orchestrator - Orquestracao continua com Temporal

Modulo responsavel pelo plano de controle duravel de cada monitoramento ativo.
Cada monitorado ativo e uma Workflow Execution independente e persistente.

Componentes:
  - workflow/          - pacote do MonitoredProductWorkflow (entrypoint + handlers)
  - activities/        - pacote de activities de integracao (Temporal <-> Celery/DB/Redis)
  - worker.py          - Temporal Worker Python
  - reconciler.py      - Reconciliador de monitorados ativos
  - alert/alert_client - TemporalOrchestrationClient (adaptador para o dominio)
  - schemas/           - Dataclasses de input/output/signals/queries
  - core/              - Configuracoes (OrchestratorSettings)

A camada de execucao existente nao foi alterada:
  - Celery workers e tasks (market_alert/tasks/)
  - CollectionEnqueuer (market_alert/infraestructure/celery/enqueuer.py)
  - payload_builders (market_alert/collectors/dispatch/payload_builders.py)
"""

from shared.schemas.shared_schemas_orchestrator import (
    CollectionPolicy,
    CompetitorChangedPayload,
    ResumeSignalPayload,
    UpdatePolicySignalPayload,
)

from market_orchestrator.enums.enums_workflow import WorkflowState
from market_orchestrator.schemas.schemas_snapshot import WorkflowSnapshot
from market_orchestrator.schemas.schemas_workflow import WorkflowInput

__all__ = [
    "WorkflowInput",
    "WorkflowState",
    "WorkflowSnapshot",
    "CollectionPolicy",
    "ResumeSignalPayload",
    "UpdatePolicySignalPayload",
    "CompetitorChangedPayload",
]
