""" Agendador simplificado de rechecagens reaproveitando o collector padrão

O módulo converte o agendamento periódico em enfileiramento direto da task
``collect_product_task`` para monitorados elegíveis. Todo controle de
concorrência fica a cargo do lock Redis do collector, mantendo o fluxo de
rechecagem idêntico ao das coletas normais e evitando estados travados em
flags de banco.
"""

from __future__ import annotations

import random
from datetime import datetime, timezone

import structlog
from sqlalchemy.orm import Session

from shared.infra.db import SessionLocal
from shared.metrics.metrics_recheck import RECHECK_SCHEDULED_TOTAL
from shared.metrics.metrics_scraper import RECHECK_ENQUEUED_TOTAL
from shared.utils.redis_client import is_scraping_suspended

from market_alert.core.celery_app import celery_app
from market_alert.core.config_alert import settings
from market_alert.crud.crud_monitored import _compute_next_check_at
from market_alert.enums.enums_products import MonitoringType, MonitoredStatus
from market_alert.models.models_products import MonitoredProduct
from market_alert.orchestrator.collector_service_orchestrator import build_monitored_payload, enqueue_collect


logger = structlog.get_logger("recheck_scheduler_task")

def _now() -> datetime:
    """ Retorna timestamp em UTC sem microssegundos para comparações consistentes """
    return datetime.now(timezone.utc).replace(microsecond=0)

def _list_due_monitored(db: Session, reference: datetime) -> list[MonitoredProduct]:
    """ Seleciona monitorados vencidos considerando `next_check_at`

    O filtro restringe a monitorados por scraping com status ativo ou pendente
    e limita a janela pelo parâmetro ``RECHECK_ENQUEUE_BATCH_SIZE`` para evitar
    rajadas grandes em um único ciclo do Beat.
    """
    return (
        db.query(MonitoredProduct)
        .filter(
            MonitoredProduct.monitoring_type == MonitoringType.scraping,
            MonitoredProduct.status.in_([MonitoredStatus.active, MonitoredStatus.pending]),
            MonitoredProduct.next_check_at.isnot(None),
            MonitoredProduct.next_check_at <= reference,
        )
        .order_by(MonitoredProduct.next_check_at)
        .limit(settings.RECHECK_ENQUEUE_BATCH_SIZE)
        .all()
    )

def _hydrate_missing_next_check(db: Session, reference: datetime, logger_bound=None) -> int:
    """ Preenche `next_check_at` ausente para evitar produtos travados no agendador """
    missing = (
        db.query(MonitoredProduct)
        .filter(
            MonitoredProduct.monitoring_type == MonitoringType.scraping,
            MonitoredProduct.status.in_([MonitoredStatus.active, MonitoredStatus.pending]),
            MonitoredProduct.next_check_at.is_(None),
        )
        .limit(settings.RECHECK_ENQUEUE_BATCH_SIZE)
        .all()
    )

    if not missing:
        return 0
    
    for monitored in missing:
        monitored.next_check_at = _compute_next_check_at(monitored, reference=reference)
    db.commit()

    bound_logger = logger_bound or logger
    bound_logger.info(
        "recheck_missing_windows_repaired",
        repaired=len(missing),
        reference=reference.isoformat(),
    )
    return len(missing)

def schedule_rechecks(
    db: Session,
    *,
    now: datetime | None = None,
    enqueue_callable=None,
    logger_bound=None,
) -> int:
    """ Agenda rechecagens vencidas aplicando jitter e reagendamento imediato

    O fluxo é propositalmente curto: identifica itens vencidos, atualiza o
    próximo agendamento com base em ``check_interval`` (ou fallback padrão) e
    enfileira a ``collect_product_task`` com jitter leve. Itens sem
    ``next_check_at`` são corrigidos automaticamente para impedir travamentos.
    """
    bound_logger = logger_bound or logger
    reference = now or _now()
    enqueue_fn = enqueue_callable or enqueue_collect

    if is_scraping_suspended():
        bound_logger.warning("recheck_skipped_scraping_suspended")
        return 0
    
    _hydrate_missing_next_check(db, reference, logger_bound=bound_logger)

    due_monitored = _list_due_monitored(db, reference)
    if not due_monitored:
        return 0
    
    jitter_limit = max(0.0, float(settings.RECHECK_ENQUEUE_JITTER_SECONDS))
    scheduled = 0

    for monitored in due_monitored:
        monitored.next_check_at = _compute_next_check_at(monitored, reference=reference)
        payload = build_monitored_payload(monitored, user_id=monitored.user_id)
        enqueue_fn(payload, countdown=random.uniform(0, jitter_limit))
        RECHECK_SCHEDULED_TOTAL.inc()
        RECHECK_ENQUEUED_TOTAL.labels(status="due").inc()
        scheduled += 1

    db.commit()
    bound_logger.info(
        "recheck_batch_scheduled",
        count=scheduled,
        reference=reference.isoformat(),
    )
    return scheduled


@celery_app.task(
    bind=True,
    max_retries=0,
    name="market_alert.tasks.recheck_scheduler_task.schedule_rechecks",
    queue="monitor",
    acks_late=True,
)
def schedule_rechecks_task(self) -> int:
    """ Task executada pelo Beat para agendar rechecagens vencidas """
    bound_logger = logger.bind(task_id=getattr(self.request, "id", None))
    with SessionLocal() as db:
        return schedule_rechecks(db, logger_bound=bound_logger)
    