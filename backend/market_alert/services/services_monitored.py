""" Consultas de leitura para produtos monitorados.

Responsabilidade única: listar e recuperar monitorados, enriquecendo com
resumos de comparação e metadados de destaque.

Este arquivo é read-only — não altera estado, não enfileira, não pausa.
Para operações de ciclo de vida (criar, pausar, deletar), use:
    market_alert.services.services_monitored_lifecycle
"""

from __future__ import annotations

from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy.orm import Session
import structlog

from market_alert.crud.crud_monitored import (
    get_all_monitored_products,
    get_featured_monitored_products,
    get_monitored_product_by_id,
    get_last_price_change_for_monitored,
)
from market_alert.crud.crud_comparison import (
    get_latest_summaries_for_products,
    get_latest_summary,
)
from market_alert.crud.crud_competitor import get_competitors_by_monitored_id
from market_alert.schemas.schemas_products import (
    MonitoredProductResponse,
    PaginatedMonitoredProductsResponse,
    PaginationMeta,
)
from market_alert.enums.enums_comparisons import CompetitivenessStatus
from market_alert.services.services_products import build_monitored_response
from market_alert.services.services_comparison import (
    persist_rebuilt_summary_if_needed,
    rebuild_summary_from_current_state,
)
from market_alert.services.services_comparison_calculator import extract_competitors_count as _extract_competitors_count
from market_alert.utils.comparison_utils import should_refresh_competitors_count as _should_refresh_competitors_count


logger = structlog.get_logger("monitored_service")

def _refresh_stale_summary_if_needed(
    *,
    db: Session,
    product_id: UUID,
    summary,
):
    """ Recalcula contagem de concorrentes quando o snapshot está defasado.

    A função protege endpoints que reutilizam snapshots de comparação e garante
    que a contagem de concorrentes reflita cadastros criados após ``computed_at``.
    """
    if summary is None:
        return summary

    competitors_count = _extract_competitors_count(summary)
    if not _should_refresh_competitors_count(
        db=db,
        monitored_id=product_id,
        summary_timestamp=summary.timestamp,
    ):
        return summary

    monitored = get_monitored_product_by_id(db, product_id)
    if monitored is None:
        return summary

    competitors = get_competitors_by_monitored_id(
        db,
        product_id,
        include_paused=True,
        include_inactive=True,
    )
    refreshed_count = len(competitors)
    normalized_summary = rebuild_summary_from_current_state(
        db=db,
        monitored=monitored,
        competitors=competitors,
        stored_summary=summary,
    )
    normalized_summary = persist_rebuilt_summary_if_needed(
        db=db,
        monitored_id=product_id,
        normalized_summary=normalized_summary,
        stored_summary=summary,
    )
    logger.info(
        "monitored_summary_competitors_count_refreshed",
        monitored_id=str(product_id),
        previous_count=competitors_count,
        refreshed_count=refreshed_count,
    )
    return normalized_summary

def list_monitored_products(
    *,
    db: Session,
    user_id: UUID,
    page: int,
    per_page: int | None,
    query: str | None = None,
    status: CompetitivenessStatus | None = None,
) -> PaginatedMonitoredProductsResponse:
    """ Agrupa monitorados em resposta paginada com resumos calculados.

    Mantém a lógica de obtenção de resumos mais recentes e montagem
    do DTO de monitorados, expondo registros pendentes ou indisponíveis mesmo
    sem preço coletado para informar o status ao usuário.
    """
    products_with_count, total, resolved_per_page = get_all_monitored_products(
        db,
        user_id,
        page=page,
        per_page=per_page,
        query=query,
        status=status,
    )

    #Protege paginação client-side quando o frontend optar por trazer todos os itens
    resolved_page = page if per_page is not None else 1

    product_ids = [product.id for product, _ in products_with_count]
    summaries_map = get_latest_summaries_for_products(db, product_ids)

    response_payload: list[MonitoredProductResponse] = []
    for product, _ in products_with_count:
        normalized_summary = _refresh_stale_summary_if_needed(
            db=db,
            product_id=product.id,
            summary=summaries_map.get(product.id),
        )
        response_payload.append(
            build_monitored_response(
                product,
                summary=normalized_summary,
                allow_missing_price=True,
            )
        )

    return PaginatedMonitoredProductsResponse(
        items=response_payload,
        meta=PaginationMeta(
            total=total,
            page=resolved_page,
            per_page=resolved_per_page,
        ),
    )

def list_featured_monitored_products(
    *, db: Session, user_id: UUID, limit: int
) -> list[MonitoredProductResponse]:
    """ Seleciona destaques e monta contratos prontos para a rota.

    Centraliza a obtenção dos resumos e aplica o mesmo tratamento de
    itens sem preço para evitar respostas inconsistentes.
    """
    featured_items = get_featured_monitored_products(db, user_id, limit=limit)
    summary_map = get_latest_summaries_for_products(
        db, [product.id for product in featured_items]
    )

    response_payload: list[MonitoredProductResponse] = []
    for product in featured_items:
        try:
            response_payload.append(
                build_monitored_response(product, summary=summary_map.get(product.id))
            )
        except HTTPException as exc:
            #Manter o contrato consistente mesmo que algum destaque esteja sem preço
            logger.warning(
                "featured_without_price",
                product_id=str(product.id),
                status=product.status.value,
                detail=str(exc.detail),
            )
            continue

    return response_payload

def get_monitored_product(
    *, db: Session, product_id: UUID, user_id: UUID
) -> MonitoredProductResponse:
    """ Recupera monitorado por ID, garantindo posse e contrato consolidado """
    product = get_monitored_product_by_id(db, product_id)
    if not product or product.user_id != user_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Produto não encontrado.",
        )

    summary = _refresh_stale_summary_if_needed(
        db=db,
        product_id=product_id,
        summary=get_latest_summary(db, product_id),
    )
    last_price_change_at = get_last_price_change_for_monitored(db, product_id)

    return build_monitored_response(
        product,
        summary=summary,
        allow_missing_price=True,
        last_price_change_at=last_price_change_at,
        global_last_price_change_at=last_price_change_at,
    )
