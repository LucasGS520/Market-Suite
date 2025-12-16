""" Orquestração e enfileiramento de coletas de produtos.

O módulo centraliza helpers para construir payloads consistentes e enfileirar
coletas na ``collect_product_task``. O mesmo fluxo atende rechecagens e
coletas manuais, garantindo que o controle de concorrência ocorra somente via
lock Redis aplicado pelo collector.
"""
from __future__ import annotations

import random
from uuid import UUID

import structlog
from sqlalchemy.orm import Session

from market_alert.core.config_alert import settings

from shared import metrics
from market_alert.models.models_products import CompetitorProduct, MonitoredProduct
from market_alert.crud.crud_competitor import get_competitors_by_monitored_id


logger = structlog.get_logger("collector_service")

def build_monitored_payload(
    monitored: MonitoredProduct,
    *,
    user_id: UUID
) -> dict[str, str]:
    """ Constrói payload padrão para coletas de monitorados """
    return {
        "kind": "monitored",
        "monitored_id": str(monitored.id),
        "user_id": str(user_id),
        "url": monitored.product_url,
        "name": monitored.name_identification,
    }

def build_competitor_payload(
    competitor: CompetitorProduct,
    *,
    user_id: UUID | None = None
) -> dict[str, str]:
    """ Constrói payload padrão para coletas de concorrentes vinculados """
    payload: dict[str, str] = {
        "kind": "competitor",
        "monitored_id": str(competitor.monitored_product_id),
        "url": competitor.product_url,
        "competitor_id": str(competitor.id),
    }
    if user_id:
        payload["user_id"] = str(user_id)
    return payload

def enqueue_collect(
    payload: dict[str, str],
    *,
    countdown: float | None = None
) -> None:
    """ Enfileira coleta na fila ``scraping`` mantendo única porta de entrada """
    from market_alert.tasks.collector_product_task import collect_product_task

    collect_product_task.apply_async(
        kwargs={"payload": payload},
        queue="scraping",
        countdown=countdown,
    )

def enqueue_monitored_collection(
    monitored: MonitoredProduct,
    *,
    user_id: UUID
) -> None:
    """ Abstrai o enfileiramento de monitorados e registra contexto em log """
    payload = build_monitored_payload(monitored, user_id=user_id)
    logger.info(
        "enqueue_monitored_collection",
        monitored_id=str(monitored.id),
        user_id=str(user_id),
    )
    enqueue_collect(payload, countdown=settings.ONBOARDING_ENQUEUE_STAGGER_SECONDS)

def enqueue_competitor_collection(
    competitor: CompetitorProduct,
    *,
    user_id: UUID | None = None,
    countdown: float | None = None,
) -> None:
    """ Enfileira coleta de concorrente mantendo padrão de payload """
    payload = build_competitor_payload(competitor, user_id=user_id)
    logger.info(
        "enqueue_competitor_collection",
        competitor_id=str(competitor.id),
        monitored_id=str(competitor.monitored_product_id),
    )
    enqueue_collect(
        payload,
        countdown=countdown if countdown is not None else settings.ONBOARDING_ENQUEUE_STAGGER_SECONDS,
    )

def enqueue_competitors_for_monitored(
    db: Session,
    monitored_id: UUID,
    *,
    batch_size: int | None = None,
    base_delay: float | None = None,
) -> None:
    """ Agenda coleta para concorrentes vinculados aplicando batching e jitter """

    try:
        resolved_batch_size = batch_size or settings.RECHECK_ENQUEUE_BATCH_SIZE
        resolved_base_delay = base_delay or settings.RECHECK_ENQUEUE_STAGGER_SECONDS

        if resolved_batch_size <= 0:
            logger.warning(
                "enqueue_competitors_skipped_by_limit",
                monitored_id=str(monitored_id),
                batch_size=resolved_batch_size,
            )
            metrics.RECHECK_ENQUEUE_SKIPPED_BY_LIMIT_TOTAL.inc()
            return

        competitors = get_competitors_by_monitored_id(db, monitored_id, include_paused=False)

        if len(competitors) == 0:
            logger.info("enqueue_competitors_skipped_none", monitored_id=str(monitored_id))
            return
        
        for batch_start in range(0, len(competitors), resolved_batch_size):
            batch = competitors[batch_start : batch_start + resolved_batch_size]
            for index_in_batch, competitor in enumerate(batch):
                position = batch_start + index_in_batch
                #Aplica atraso incremental com jitter curto para diluir picos de scraping
                jitter = random.uniform(-0.5, 0.5) * resolved_base_delay * 0.1
                countdown = max(0.0, resolved_base_delay * position + jitter)
                try:
                    enqueue_competitor_collection(
                        competitor,
                        countdown=countdown,
                    )
                    metrics.RECHECK_COMPETITORS_ENQUEUED_TOTAL.inc()
                except Exception:
                    logger.error(
                        "enqueue_competitor_failed",
                        monitored_id=str(monitored_id),
                        competitor_id=str(competitor.id),
                        exc_info=True,
                    )
                    metrics.RECHECK_ENQUEUE_FAILURES_TOTAL.inc()
    except Exception:
        logger.error(
            "enqueue_competitors_unexpected_error",
            monitored_id=str(monitored_id),
            exc_info=True,
        )
        metrics.RECHECK_ENQUEUE_FAILURES_TOTAL.inc()


__all__ = [
    "enqueue_collect",
    "enqueue_monitored_collection",
    "enqueue_competitor_collection",
    "enqueue_competitors_for_monitored",
]
