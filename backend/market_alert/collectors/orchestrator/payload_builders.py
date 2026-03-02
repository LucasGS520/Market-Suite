""" Builders de payload para coleta de monitorados e concorrentes

Este módulo foi extraído da orquestração para evitar dependência circular
entre ``collector_service_orchestrator`` e ``CollectionEnqueuer``.
"""

from __future__ import annotations

from uuid import UUID

import structlog

from shared.utils.url_validation import normalize_competitor_url

from market_alert.models.models_products import CompetitorProduct, MonitoredProduct
from market_alert.schemas.schemas_collection_payload import CollectionPayload


logger = structlog.get_logger("payload_builders")

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
    """Monta o payload de coleta de concorrente para envio à fila.

    Objetivo:
        Padronizar os dados do ``CompetitorProduct`` no contrato
        ``CollectionPayload`` utilizado pelo enfileiramento de scraping.

    Campos esperados:
        ``competitor.id``, ``competitor.monitored_product_id``,
        ``competitor.product_url`` e ``competitor.name_competitor``.

    Comportamento em inconsistências:
        Quando ``name_competitor`` estiver ausente ou vazio, o payload não é
        gerado. Nesse caso, o builder registra log estruturado com contexto do
        concorrente e levanta ``ValueError`` para interromper o enfileiramento
        inválido.
    """
    normalized_url = normalize_competitor_url(competitor.product_url)
    resolved_url = normalized_url or competitor.product_url
    raw_name_competitor = str(getattr(competitor, "name_competitor", "") or "").strip()

    if not raw_name_competitor:
        logger.warning(
            "competitor_payload_rejected_missing_name",
            competitor_id=str(getattr(competitor, "id", "")),
            product_id=str(getattr(competitor, "monitored_product_id", "")),
            reason="missing_name_competitor",
        )
        raise ValueError("CompetitorProduct inválido para fila: name_competitor ausente ou vazio")

    resolved_name = (
        str(getattr(competitor, "display_name", "") or "").strip()
        or raw_name_competitor
        or str(resolved_url or "").strip()
        or "unknown_competitor"
    )
    return CollectionPayload(
        kind="competitor",
        monitored_id=competitor.monitored_product_id,
        competitor_id=competitor.id,
        url=resolved_url,
        name=resolved_name,
        trace_id=trace_id or "",
        enqueued_at=enqueued_at,
    )


__all__ = ["build_monitored_payload", "build_competitor_payload"]
