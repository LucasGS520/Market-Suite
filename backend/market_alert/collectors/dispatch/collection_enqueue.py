""" Dispatch/enfileiramento de coletas de produtos.

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
from typing import TYPE_CHECKING
from uuid import UUID

import structlog
from sqlalchemy.orm import Session

from shared.schemas.shared_schemas_orchestrator import CollectionPayload

from market_alert.core.config_alert import settings
from market_alert.models.models_products import CompetitorProduct, MonitoredProduct
from market_alert.products.crud.crud_competitor import get_competitors_by_monitored_id
from market_alert.collectors.dispatch.payload_builders import build_competitor_payload, build_monitored_payload

if TYPE_CHECKING:
    from market_alert.infraestructure.celery.enqueuer import CollectionEnqueuer


logger = structlog.get_logger("collector_service")
_enqueuer: CollectionEnqueuer | None = None

def _get_enqueuer() -> CollectionEnqueuer:
    """ Retorna uma instância lazy de ``CollectionEnqueuer`` para o orquestrador.

    A inicialização tardia evita carregar dependências pesadas e reduz risco de
    import circular durante o bootstrap do Celery.
    """
    global _enqueuer
    if _enqueuer is None:
        #Import local para quebrar ciclo entre dispatch e enqueuer
        from market_alert.infraestructure.celery.enqueuer import CollectionEnqueuer

        _enqueuer = CollectionEnqueuer()
    return _enqueuer

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

    _get_enqueuer()._send(payload, countdown=countdown)

def enqueue_monitored_collection(
    monitored: MonitoredProduct,
    *,
    user_id: UUID,
    trace_id: str | None = None,
) -> None:
    """ Abstrai o enfileiramento de monitorados e registra contexto em log."""
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
    user_id: UUID,
    countdown: float | None = None,
    trace_id: str | None = None,
) -> None:
    """ Enfileira coleta de concorrente mantendo padrão de payload tipado."""
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
    """ Agenda coleta para concorrentes vinculados aplicando batching e jitter."""
    try:
        resolved_batch_size = batch_size or 20
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
                    monitored_owner = competitor.monitored_product
                    if monitored_owner is None or monitored_owner.user_id is None:
                        logger.warning(
                            "enqueue_competitor_skipped_missing_user",
                            monitored_id=str(monitored_id),
                            competitor_id=str(competitor.id),
                        )
                        continue

                    enqueue_competitor_collection(
                        competitor,
                        user_id=monitored_owner.user_id,
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
    "enqueue_collect",
    "enqueue_monitored_collection",
    "enqueue_competitor_collection",
    "enqueue_competitors_for_monitored",
]
