""" Orquestração e enfileiramento de coletas de produtos.

O módulo centraliza helpers para construir payloads consistentes e enfileirar
coletas na ``collect_product_task``. O mesmo fluxo atende rechecagens e
coletas manuais, garantindo que o controle de concorrência ocorra somente via
lock Redis aplicado pelo collector.
"""
from __future__ import annotations

from uuid import UUID

import structlog
from sqlalchemy.orm import Session

from market_alert.core.config_alert import settings

from market_alert.models.models_products import CompetitorProduct, MonitoredProduct
from market_alert.crud.crud_competitor import get_competitors_by_monitored_id


logger = structlog.get_logger("collector_service")

def build_monitored_payload(monitored: MonitoredProduct, *, user_id: UUID) -> dict[str, str]:
    """ Constrói payload padrão para coletas de monitorados """
    return {
        "kind": "monitored",
        "monitored_id": str(monitored.id),
        "user_id": str(user_id),
        "url": monitored.product_url,
        "name": monitored.name_identification,
    }
def build_competitor_payload(competitor: CompetitorProduct, *, user_id: UUID | None = None) -> dict[str, str]:
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

def enqueue_collect(payload: dict[str, str], *, countdown: float | None = None) -> None:
    """ Enfileira coleta na fila ``scraping`` mantendo única porta de entrada """
    from market_alert.tasks.collector_product_task import collect_product_task

    collect_product_task.apply_async(
        kwargs={"payload": payload},
        queue="scraping",
        countdown=countdown,
    )

def enqueue_monitored_collection(monitored: MonitoredProduct, *, user_id: UUID) -> None:
    """ Abstrai o enfileiramento de monitorados e registra contexto em log """
    payload = build_monitored_payload(monitored, user_id=user_id)
    logger.info(
        "enqueue_monitored_collection",
        monitored_id=str(monitored.id),
        user_id=str(user_id),
    )
    enqueue_collect(payload, countdown=settings.ONBOARDING_ENQUEUE_STAGGER_SECONDS)

def enqueue_competitor_collection(competitor: CompetitorProduct, *, user_id: UUID | None = None) -> None:
    """ Enfileira coleta de concorrente mantendo padrão de payload """
    payload = build_competitor_payload(competitor, user_id=user_id)
    logger.info(
        "enqueue_competitor_collection",
        competitor_id=str(competitor.id),
        monitored_id=str(competitor.monitored_product_id),
    )
    enqueue_collect(payload, countdown=settings.ONBOARDING_ENQUEUE_STAGGER_SECONDS)

def enqueue_competitors_for_monitored(db: Session, monitored_id: UUID) -> None:
    """ Agenda coleta apenas para concorrentes vinculados ao monitorado informado """
    competitors = get_competitors_by_monitored_id(db, monitored_id)
    for competitor in competitors:
        enqueue_competitor_collection(competitor)


__all__ = [
    "enqueue_collect",
    "enqueue_monitored_collection",
    "enqueue_competitor_collection",
    "enqueue_competitors_for_monitored",
]
