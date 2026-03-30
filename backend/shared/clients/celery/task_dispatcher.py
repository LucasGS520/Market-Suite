""" Interface neutra para enfileiramento de coletas no Celery.

Permite que módulos externos (ex: market_orchestrator) disparem coletas
sem importar market_alert. Usa send_task() por nome de string — não importa
nenhum código de market_alert.
"""
from __future__ import annotations

import structlog
from celery import Celery


logger = structlog.get_logger("shared.celery.task_dispatcher")

# Nome canônico da task de coleta — string pura, sem import de market_alert
_COLLECT_TASK_NAME = (
    "market_alert.collectors.tasks.collector_product_task.collect_product_task"
)
_SCRAPING_QUEUE = "scraping"

_sender: Celery | None = None

def _get_sender() -> Celery:
    """ Retorna app Celery mínima para envio de tasks (lazy, sem registro de tasks)."""
    global _sender
    if _sender is None:
        from shared.core.config_base import ConfigBase
        cfg = ConfigBase()
        _sender = Celery(broker=cfg.celery_broker_url)
    return _sender

def send_collection_task(payload_dict: dict) -> str:
    """ Enfileira coleta na fila Celery 'scraping' sem importar market_alert.

    Args:
        payload_dict: dict serializado de CollectionPayload (model_dump(mode='json')).

    Returns:
        task_id (str) da AsyncResult gerada pelo Celery.
    """
    result = _get_sender().send_task(
        _COLLECT_TASK_NAME,
        kwargs={"payload": payload_dict},
        queue=_SCRAPING_QUEUE,
    )
    logger.debug(
        "send_collection_task_dispatched",
        task_id=result.id,
        queue=_SCRAPING_QUEUE,
    )
    return result.id
