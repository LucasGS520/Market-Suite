""" Task Celery de reconciliação periódica de workflows Temporal.

Garante que nenhum monitorado ativo fique sem workflow após falha de infra
ou gap de estado. Execução de baixa frequência (a cada 10 minutos via Beat).
"""
from __future__ import annotations

import structlog
from celery import shared_task

logger = structlog.get_logger("reconciler_task")


@shared_task(
    name="market_alert.infraestructure.tasks.reconciler_task.reconcile_workflows_task",
    bind=True,
    max_retries=0, #Não retentar — próxima execução do Beat resolve
    ignore_result=True,
)
def reconcile_workflows_task(self) -> None:
    """ Executa reconciliação de workflows Temporal para monitorados ativos.

    Falhas de conexão com o Temporal são silenciadas — o sistema continua
    operando sem o orquestrador (fallback não-bloqueante do cliente).
    """
    try:
        from market_orchestrator.reconciler import WorkflowReconciler

        reconciler = WorkflowReconciler()
        counts = reconciler.reconcile_all()
        logger.info("reconcile_workflows_task_done", **counts)

    except Exception as exc:
        #Silencia falha total — não interrompe demais workers
        logger.error("reconcile_workflows_task_error", error=str(exc))
