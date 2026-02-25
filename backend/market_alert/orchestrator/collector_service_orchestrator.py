""" Orquestração e enfileiramento de coletas de produtos.

O módulo centraliza helpers para construir payloads consistentes e enfileirar
coletas na ``collect_product_task``. O mesmo fluxo atende rechecagens e
coletas manuais, garantindo que o controle de concorrência ocorra somente via
lock Redis aplicado pelo collector.

Contrato de payload:
    Todos os builders retornam ``CollectionPayload`` tipado (Pydantic).
    Ao enfileirar no Celery, o payload é serializado via ``.model_dump(mode='json')``.
    Isso garante validação na origem e compatibilidade com a fila de dicts do Celery.
"""
from __future__ import annotations

import random
from uuid import UUID

import structlog
from sqlalchemy.orm import Session

from market_alert.core.config_alert import settings
from market_alert.crud.crud_competitor import get_competitors_by_monitored_id
from market_alert.models.models_products import CompetitorProduct, MonitoredProduct
from market_alert.orchestrator.collection_enqueuer import CollectionEnqueuer
from market_alert.schemas.schemas_collection_payload import CollectionPayload
from shared.utils.url_validation import normalize_competitor_url

_enqueuer = CollectionEnqueuer()


logger = structlog.get_logger("collector_service")


def build_monitored_payload(
    monitored: MonitoredProduct,
    *,
    user_id: UUID,
    enqueued_at: str | None = None,
    trace_id: str | None = None,
) -> CollectionPayload:
    """ Constrói payload tipado para coletas de monitorados.

    O ``trace_id`` é gerado automaticamente pelo ``CollectionPayload`` se não
    informado, garantindo rastreamento mesmo em chamadas legadas.
    """
    resolved_url = monitored.normalized_url or monitored.product_url
    return CollectionPayload(
        kind="monitored",
        monitored_id=monitored.id,
        user_id=user_id,
        url=resolved_url,
        name=monitored.name_identification,
        trace_id=trace_id or "",
        enqueued_at=enqueued_at,
    )


def build_competitor_payload(
    competitor: CompetitorProduct,
    *,
    user_id: UUID | None = None,
    enqueued_at: str | None = None,
    trace_id: str | None = None,
) -> CollectionPayload:
    """ Constrói payload tipado para coletas de concorrentes vinculados.

    O ``trace_id`` é gerado automaticamente se não informado.
    """
    normalized_url = normalize_competitor_url(competitor.product_url)
    resolved_url = normalized_url or competitor.product_url
    return CollectionPayload(
        kind="competitor",
        monitored_id=competitor.monitored_product_id,
        competitor_id=competitor.id,
        url=resolved_url,
        name=competitor.name_competitor,
        user_id=user_id,
        trace_id=trace_id or "",
        enqueued_at=enqueued_at,
    )


def enqueue_collect(
    payload: CollectionPayload | dict,
    *,
    countdown: float | None = None,
) -> None:
    """ Wrapper de compatibilidade — delega ao ``CollectionEnqueuer``.

    Aceita ``CollectionPayload`` (novo padrão) ou ``dict`` (legado).
    O enfileiramento real ocorre exclusivamente em ``CollectionEnqueuer._send()``.
    """
    if isinstance(payload, dict):
        #Converte payload legado para ``CollectionPayload`` antes de enfileirar
        payload = CollectionPayload.model_validate(payload)

    _enqueuer._send(payload, countdown=countdown)


def enqueue_monitored_collection(
    monitored: MonitoredProduct,
    *,
    user_id: UUID,
    trace_id: str | None = None,
) -> None:
    """ Abstrai o enfileiramento de monitorados e registra contexto em log """
    #Se o monitorado estiver pausado, não enfileira para preservar o contrato de pausa
    if getattr(monitored, "paused", False):
        logger.info(
            "enqueue_skipped_monitored_paused",
            monitored_id=str(monitored.id),
            user_id=str(user_id),
        )
        return

    payload = build_monitored_payload(monitored, user_id=user_id, trace_id=trace_id)
    logger.info(
        "enqueue_monitored_collection",
        monitored_id=str(monitored.id),
        user_id=str(user_id),
        trace_id=payload.trace_id,
    )
    enqueue_collect(payload, countdown=settings.ONBOARDING_ENQUEUE_STAGGER_SECONDS)


def enqueue_competitor_collection(
    competitor: CompetitorProduct,
    *,
    user_id: UUID | None = None,
    countdown: float | None = None,
    trace_id: str | None = None,
) -> None:
    """ Enfileira coleta de concorrente mantendo padrão de payload tipado """
    payload = build_competitor_payload(competitor, user_id=user_id, trace_id=trace_id)
    logger.info(
        "enqueue_competitor_collection",
        competitor_id=str(competitor.id),
        monitored_id=str(competitor.monitored_product_id),
        trace_id=payload.trace_id,
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
        resolved_batch_size = batch_size or settings.CONTINUOUS_WORKER_BATCH_SIZE
        resolved_base_delay = base_delay or settings.ONBOARDING_ENQUEUE_STAGGER_SECONDS

        if resolved_batch_size <= 0:
            logger.warning(
                "enqueue_competitors_skipped_by_limit",
                monitored_id=str(monitored_id),
                batch_size=resolved_batch_size,
            )
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
                except Exception:
                    logger.error(
                        "enqueue_competitor_failed",
                        monitored_id=str(monitored_id),
                        competitor_id=str(competitor.id),
                        exc_info=True,
                    )
    except Exception:
        logger.error(
            "enqueue_competitors_unexpected_error",
            monitored_id=str(monitored_id),
            exc_info=True,
        )


__all__ = [
    "build_monitored_payload",
    "build_competitor_payload",
    "enqueue_collect",
    "enqueue_monitored_collection",
    "enqueue_competitor_collection",
    "enqueue_competitors_for_monitored",
]
