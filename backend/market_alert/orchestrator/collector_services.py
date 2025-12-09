""" Orquestração e enfileiramento de coletas de produtos.

Este módulo concentra helpers que padronizam a criação de payloads para a
``collect_product_task`` e a varredura periódica de monitorados. A proposta
é manter rotas e services finos, delegando aqui toda a coordenação de filas
(e o balanceamento entre monitorados e concorrentes) em uma única camada.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import UUID

import structlog
from sqlalchemy.orm import Session

from shared.metrics.metrics_scraper import RECHECK_DISPATCH_TOTAL

from market_alert.core.config_alert import settings

from market_alert.enums.enums_products import MonitoringType, MonitoredStatus
from market_alert.models.models_products import CompetitorProduct, MonitoredProduct
from market_alert.crud.crud_competitor import get_competitors_by_monitored_id
from market_alert.crud.crud_monitored import get_products_by_type


logger = structlog.get_logger("collector_service")

def _now() -> datetime:
    """ Retorna timestamp em UTC sem microssegundos para cálculos previsíveis """
    return datetime.now(timezone.utc).replace(microsecond=0)

def _default_interval_seconds(monitored: MonitoredProduct) -> int:
    """ Determina o intervalo mínimo entre coletas usando o atributo dinamicamente.

    Quando o modelo não possuir campo específico, utiliza o valor configurado
    em ``ADAPTIVE_RECHECK_BASE_INTERVAL`` como fallback seguro.
    """
    dynamic_interval = getattr(monitored, "check_interval", None)
    if isinstance(dynamic_interval, int) and dynamic_interval > 0:
        return dynamic_interval
    return int(settings.ADAPTIVE_RECHECK_BASE_INTERVAL)

def monitored_needs_recheck(monitored: MonitoredProduct, *, now: datetime | None = None) -> bool:
    """ Aplica janela mínima entre checagens para evitar reprocessamento agressivo """
    reference = monitored.last_checked or monitored.updated_at or monitored.created_at
    if reference is None:
        return True
    current_time = now or _now()
    return current_time - reference >= timedelta(seconds=_default_interval_seconds(monitored))

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

def enqueue_collect(payload: dict[str, str]) -> None:
    """ Enfileira coleta na fila ``scraping`` mantendo única porta de entrada """
    from market_alert.tasks.collector_tasks import collect_product_task

    collect_product_task.apply_async(kwargs={"payload": payload}, queue="scraping")

def enqueue_monitored_collection(monitored: MonitoredProduct, *, user_id: UUID) -> None:
    """ Abstrai o enfileiramento de monitorados e registra contexto em log """
    payload = build_monitored_payload(monitored, user_id=user_id)
    logger.info(
        "enqueue_monitored_collection",
        monitored_id=str(monitored.id),
        user_id=str(user_id),
    )
    enqueue_collect(payload)

def enqueue_competitor_collection(competitor: CompetitorProduct, *, user_id: UUID | None = None) -> None:
    """ Enfileira coleta de concorrente mantendo padrão de payload """
    payload = build_competitor_payload(competitor, user_id=user_id)
    logger.info(
        "enqueue_competitor_collection",
        competitor_id=str(competitor.id),
        monitored_id=str(competitor.monitored_product_id),
    )
    enqueue_collect(payload)

def enqueue_competitors_for_monitored(db: Session, monitored_id: UUID) -> None:
    """ Agenda coleta apenas para concorrentes vinculados ao monitorado informado """
    competitors = get_competitors_by_monitored_id(db, monitored_id)
    for competitor in competitors:
        enqueue_competitor_collection(competitor)

def schedule_due_monitored(db: Session, *, now: datetime | None = None) -> int:
    """ Varre monitorados e agenda rechecagens somente quando elegíveis.

    A rotina respeita ``next_check_at`` e ignora itens com ``checking_in_progress``
    a menos que já tenham estourado o tempo máximo configurado em
    ``RECHECK_TIMEOUT_SECONDS``.
    """
    from market_alert.tasks.monitor_tasks import recheck_monitored_products

    reference = now or _now()
    timeout_limit = reference - timedelta(seconds=settings.RECHECK_TIMEOUT_SECONDS)
    candidates = get_products_by_type(db, MonitoringType.scraping)
    dispatched = 0

    for monitored in candidates:
        if monitored.status == MonitoredStatus.failed:
            RECHECK_DISPATCH_TOTAL.labels(status="skip_failed").inc()
            continue
        
        if monitored.checking_in_progress:
            started_at = monitored.checking_started_at
            if started_at is None or started_at < timeout_limit:
                monitored.checking_in_progress = False
                monitored.checking_started_at = None
                monitored.next_check_at = reference
                db.commit()
                logger.warning(
                    "recheck_timeout_released",
                    monitored_id=str(monitored.id),
                    started_at=str(started_at) if started_at else None,
                )
            else:
                RECHECK_DISPATCH_TOTAL.labels(status="skip_in_progress").inc()
                logger.info(
                    "recheck_skip_in_progress",
                    monitored_id=str(monitored.id),
                )
                continue

        next_run = monitored.next_check_at
        if next_run and next_run > reference:
            RECHECK_DISPATCH_TOTAL.labels(status="not_due").inc()
            continue
        
        enqueue_kwargs = {"args": [str(monitored.id)], "queue": "monitor"}
        recheck_monitored_product.apply_async(**enqueue_kwargs)
        RECHECK_DISPATCH_TOTAL.labels(status="dispatched").inc()
        dispatched += 1
    return dispatched


__all__ = [
    "enqueue_collect",
    "enqueue_monitored_collection",
    "enqueue_competitor_collection",
    "enqueue_competitors_for_monitored",
    "schedule_due_monitored",
    "monitored_needs_recheck",
]
