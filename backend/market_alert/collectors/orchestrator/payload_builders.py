""" Builders de payload para coleta de monitorados e concorrentes

Este módulo foi extraído da orquestração para evitar dependência circular
entre ``collector_service_orchestrator`` e ``CollectionEnqueuer``.
"""

from __future__ import annotations

from uuid import UUID

from shared.utils.url_validation import normalize_competitor_url

from market_alert.models.models_products import CompetitorProduct, MonitoredProduct
from market_alert.schemas.schemas_collection_payload import CollectionPayload


def build_monitored_payload(
    monitored: MonitoredProduct,
    *,
    user_id: UUID,
    enqueued_at: str | None = None,
    trace_id: str | None = None,
) -> CollectionPayload:
    """ Constrói payload tipado para coletas de monitorados """
    resolved_url = monitored.normalized_url or monitored.product_url
    return CollectionPayload(
        kind="monitored",
        monitored_id=monitored.id,
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
    """ Constrói payload tipado para coletas de concorrentes vinculados """
    normalized_url = normalize_competitor_url(competitor.product_url)
    resolved_url = normalized_url or competitor.product_url
    return CollectionPayload(
        kind="competitor",
        monitored_id=competitor.monitored_product_id,
        competitor_id=competitor.id,
        url=resolved_url,
        name=competitor.name_identification,
        trace_id=trace_id or "",
        enqueued_at=enqueued_at,
    )


__all__ = ["build_monitored_payload", "build_competitor_payload"]
