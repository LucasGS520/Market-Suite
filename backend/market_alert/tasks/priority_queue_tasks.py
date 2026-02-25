""" Task de reconciliação da fila de prioridade de monitorados.

Esta task garante que monitorados ativos e não pausados estejam presentes na
fila Redis, utilizando o ``next_check_at`` como referência de agendamento.

A lógica de reconciliação está em ``orchestrator.collection_reconciliation``
e usa flag Redis para evitar execuções simultâneas.
"""

from __future__ import annotations

from shared.infra.db import SessionLocal

from market_alert.core.celery_app import celery_app
from market_alert.orchestrator.collection_reconciliation import reconcile_collection_queue


@celery_app.task(name="market_alert.tasks.priority_queue_tasks.reconcile_priority_queue")
def reconcile_priority_queue() -> dict[str, int]:
    """ Recarrega a fila de prioridade com monitorados ativos.

    Delega para ``reconcile_collection_queue()`` que:
    - Usa flag Redis para evitar reconciliações simultâneas.
    - Acessa a fila exclusivamente via ``CollectionQueue``.
    - Retorna estatísticas de enfileiramento para auditoria.
    """
    with SessionLocal() as db:
        return reconcile_collection_queue(db)
