""" Serviço de orquestração de comparação de preços

Responsabilidade única: coordenar o fluxo completo de comparação —
autorização, carregamento, cálculo, idempotência e persistência.

Este arquivo NÃO contém:
- Lógica de cálculo (→ services_comparison_calculator.py)
- Filtragem e carregamento de produtos (→ services_comparison_utils.py)
- Regras de competitividade (→ domain/price_competitiveness.py)
- Comparação de snapshots (→ utils/snapshot_comparator.py)

Fluxo principal:
    API/Task → run_price_comparison()
        → load_monitored_and_competitors()     [utils]
        → resolve_monitored_inactive_reason()  [calculator]
        → compare_prices()                     [price_comparator]
        → _persist_comparison_result()         [aqui, orquestra CRUD]
        → retorno para consumidores
"""

from uuid import UUID
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from decimal import Decimal

import structlog
from fastapi import HTTPException, status
from fastapi.encoders import jsonable_encoder
from sqlalchemy.orm import Session

from shared.schemas.collection_catalog import NEUTRAL_REASONS

from market_alert.core.config_alert import settings
from market_alert.models import User
from market_alert.models.models_comparisons import PriceComparisonSummary
from market_alert.models.models_products import CompetitorProduct
from market_alert.schemas.schemas_comparisons import PriceComparisonResponse, PriceComparisonSummaryResponse
from market_alert.comparisons.crud.crud_comparison import (
    create_price_comparison,
    get_comparison_by_id,
    get_latest_summary,
    upsert_price_comparison_summary,
)
from market_alert.comparisons.services.products_access import get_competitors_for_monitored, get_monitored_by_id
from market_alert.comparisons.services.services_comparison_calculator import (
    apply_summary_defaults,
    compute_summary_from_payload,
    rebuild_summary_from_current_state,
    resolve_monitored_inactive_reason,
    summarize_comparison,
)
from market_alert.comparisons.utils.comparison_utils import load_monitored_and_competitors
from market_alert.comparisons.utils.price_comparator import compare_prices
from market_alert.comparisons.utils.snapshot_comparator import extract_material_snapshot, snapshot_has_changed


logger = structlog.get_logger("comparison_service")

#Mapeamento de razão interna de inatividade → upstream_reason no catálogo de comparação.
#Permite que consumidores distingam falha de coleta de produto genuinamente inativo.
_INACTIVE_REASON_TO_UPSTREAM: dict[str, str] = {
    "paused": "ignored_due_to_inactive",
    "monitored_unavailable": "skipped_due_to_monitored_unavailable",
    "monitored_without_price": "upstream_collection_failed",
}

#Re-exporta summarize_comparison para consumidores legados
#(services_products.py e outros que importam daqui)
__all__ = [
    "ensure_user_can_view_monitored",
    "get_comparison_summary_for_user",
    "get_comparison_detail_for_user",
    "run_price_comparison",
    "persist_rebuilt_summary_if_needed",
    "rebuild_summary_from_current_state",
    "summarize_comparison",
]

def ensure_user_can_view_monitored(
    *, db: Session, monitored_id: UUID, user: User
) -> None:
    """ Valida se o monitorado pertence ao usuário autenticado """
    from market_alert.products.services.services_access_control import ensure_user_can_access_monitored

    return ensure_user_can_access_monitored(
        db=db,
        product_id=monitored_id,
        user=user,
        context={"monitored_id": str(monitored_id)},
    )

def get_comparison_summary_for_user(
    *, db: Session, monitored_id: UUID, user: User
) -> PriceComparisonSummaryResponse:
    """ Retorna o resumo mais recente garantindo que o produto pertença ao usuário.

    Fluxo:
    1. Valida autorização
    2. Carrega monitorado e todos os concorrentes (incluindo pausados)
    3. Recompõe resumo a partir do estado atual
    4. Persiste se houver mudança material
    5. Retorna resposta formatada
    """
    ensure_user_can_view_monitored(db=db, monitored_id=monitored_id, user=user)

    stored_summary = get_latest_summary(db, monitored_product_id=monitored_id)
    monitored = get_monitored_by_id(db, monitored_id)
    if monitored is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Produto monitorado não encontrado.",
        )

    competitors = get_competitors_for_monitored(
        db,
        monitored_id,
        include_paused=True,
        include_inactive=True,
    )

    normalized_summary = rebuild_summary_from_current_state(
        db=db,
        monitored=monitored,
        competitors=competitors,
        stored_summary=stored_summary,
    )

    normalized_summary = persist_rebuilt_summary_if_needed(
        db=db,
        monitored_id=monitored_id,
        normalized_summary=normalized_summary,
        stored_summary=stored_summary,
    )

    return PriceComparisonSummaryResponse(
        monitored_product_id=monitored_id, **normalized_summary
    )

def get_comparison_detail_for_user(
    *,
    db: Session,
    comparison_id: UUID,
    user: User,
) -> PriceComparisonResponse:
    """ Retorna detalhes de comparação apenas quando pertence ao usuário """
    comparison = get_comparison_by_id(db, comparison_id)
    if comparison is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Comparação não encontrada.",
        )

    ensure_user_can_view_monitored(
        db=db, monitored_id=comparison.monitored_product_id, user=user
    )
    return comparison

def persist_rebuilt_summary_if_needed(
    *,
    db: Session,
    monitored_id: UUID,
    normalized_summary: Dict[str, Any],
    stored_summary: PriceComparisonSummary | None,
) -> Dict[str, Any]:
    """ Persiste resumo recomposto apenas quando houver mudança material.

    Comportamentos defensivos deste fluxo:
    - recusa payload inválido (não-dict)
    - valida/converte comparison_id antes do upsert
    - evita escrita quando snapshot material não mudou
    - registra erro com contexto e retorna payload candidato em caso de falha

    Isso mantém a operação idempotente, observável e resiliente a dados parciais.
    """
    if not isinstance(normalized_summary, dict):
        logger.warning(
            "comparison_summary_invalid_payload",
            monitored_id=str(monitored_id),
            payload_type=type(normalized_summary).__name__,
        )
        return {}
    
    comparison_raw = normalized_summary.get("comparison_id")
    if comparison_raw is None and stored_summary is not None:
        comparison_raw = stored_summary.comparison_id

    if comparison_raw is None:
        #Sem comparação associada não há chave estável para upsert
        return normalized_summary

    comparison_id = comparison_raw
    if isinstance(comparison_id, str):
        try:
            comparison_id = UUID(comparison_id)
        except ValueError:
            logger.warning(
                "comparison_summary_invalid_comparison_id",
                monitored_id=str(monitored_id),
                comparison_id_raw=comparison_raw,
            )
            return normalized_summary

    candidate_summary = dict(normalized_summary)
    candidate_summary["comparison_id"] = str(comparison_id)

    previous_snapshot = extract_material_snapshot(
        stored_summary.aggregates if stored_summary is not None else {}
    )
    current_snapshot = extract_material_snapshot(candidate_summary)

    if not snapshot_has_changed(current_snapshot, previous_snapshot):
        #Dados idênticos — evita escrita desnecessária no banco
        logger.debug(
            "comparison_summary_unchanged",
            monitored_id=str(monitored_id),
            comparison_id=str(comparison_id),
        )
        return candidate_summary

    try:
        persisted_summary = upsert_price_comparison_summary(
            db,
            monitored_id,
            comparison_id,
            jsonable_encoder(candidate_summary),
        )
    except Exception:
        logger.exception(
            "comparison_summary_persist_failed",
            monitored_id=str(monitored_id),
            comparison_id=str(comparison_id),
        )
        return candidate_summary
    
    logger.info(
        "comparison_summary_persisted",
        monitored_id=str(monitored_id),
        comparison_id=str(comparison_id),
    )
    return apply_summary_defaults(
        persisted_summary.aggregates or {},
        timestamp=persisted_summary.timestamp,
        comparison_id=persisted_summary.comparison_id,
        competitors_count=_extract_competitors_count_from_summary(persisted_summary),
    )

def run_price_comparison(
    db: Session,
    monitored_id: UUID,
    tolerance: Optional[Decimal] = None,
) -> Dict[str, Any]:
    """ Executa comparação de preços e retorna resumo persistido para o monitorado.

    Ponto de entrada único para comparação acionada por tasks ou orquestrador.
    Não requer usuário autenticado — a autorização é responsabilidade do caller.

    Fluxo:
    1. Carrega monitorado e filtra concorrentes
    2. Se monitorado inativo → persiste stub e retorna early
    3. Executa compare_prices() (cálculo puro em price_comparator)
    4. Persiste PriceComparison + PriceComparisonSummary
    5. Retorna resultado com summary embutido

    Args:
        db: Sessão ativa do banco de dados.
        monitored_id: UUID do produto monitorado.
        tolerance: Tolerância decimal para cálculo de discrepâncias.
            None usa o valor de settings.PRICE_TOLERANCE.

    Returns:
        Dict com chaves: summary, comparison_id, monitored_id, user_id,
        lowest_competitor, highest_competitor.

    Raises:
        ValueError: Se o monitorado não for encontrado.
    """
    monitored, available_competitors, _, total_competitors = (
        load_monitored_and_competitors(db, monitored_id)
    )

    if getattr(monitored, "paused", False):
        logger.info(
            "comparison_skipped_paused",
            monitored_id=str(monitored_id),
            competitors_count=total_competitors,
        )
        return _persist_inactive_comparison(
            db, monitored=monitored, reason="paused", total=total_competitors
        )

    inactive_reason = resolve_monitored_inactive_reason(monitored)
    if inactive_reason:
        # Propaga o reason tipado da última coleta como upstream_reason específico,
        # permitindo que o resumo de comparação indique "http_429" ou "challenge_detected"
        # em vez do genérico "upstream_collection_failed".
        # Reasons neutros (lock_skipped, paused, etc.) não representam falha do produto
        # e por isso são descartados — o mapeamento interno de _INACTIVE_REASON_TO_UPSTREAM
        # já cobre esses casos com semântica adequada.
        _last_reason = getattr(monitored, "last_collection_reason", None)
        _upstream_reason = (
            _last_reason
            if _last_reason and _last_reason not in NEUTRAL_REASONS
            else None
        )
        logger.info(
            "comparison_skipped_inactive_monitored",
            monitored_id=str(monitored_id),
            reason=inactive_reason,
            upstream_reason=_upstream_reason,
            competitors_count=total_competitors,
        )
        return _persist_inactive_comparison(
            db,
            monitored=monitored,
            reason=inactive_reason,
            total=total_competitors,
            upstream_reason=_upstream_reason,
        )

    if monitored.current_price is None:
        logger.info(
            "comparison_no_monitored_price",
            monitored_id=str(monitored_id),
            competitors_count=total_competitors,
            note="competitiveness_status will be None without a monitored reference price",
        )

    logger.info(
        "comparison_started",
        monitored_id=str(monitored_id),
        competitors_count=total_competitors,
        competitors_with_price_count=len(available_competitors),
    )

    tol = tolerance if tolerance is not None else Decimal(str(settings.PRICE_TOLERANCE))
    raw_result = compare_prices(monitored, available_competitors, tol)
    encoded_result = jsonable_encoder(raw_result)
    persisted_result = _persist_comparison_result(
        db,
        monitored=monitored,
        result=encoded_result,
        total=total_competitors,
        available=available_competitors,
    )
    logger.info("comparison_finished", monitored_id=str(monitored_id))
    return persisted_result


# ---------------------------------------------------------------------------
# Funções internas de persistência
# ---------------------------------------------------------------------------

def _persist_inactive_comparison(
    db: Session,
    *,
    monitored: Any,
    reason: str,
    total: int,
    upstream_reason: str | None = None,
) -> Dict[str, Any]:
    """ Persiste comparação stub para monitorado inativo/sem dados e retorna resultado.

    upstream_reason distingue falha upstream de produto genuinamente inativo:
    - skipped_due_to_monitored_unavailable: produto indisponível confirmado.
    - upstream_collection_failed: preço ausente por falha de coleta anterior.
    - ignored_due_to_inactive: produto pausado/inativo intencionalmente.
    """
    resolved_upstream = upstream_reason or _INACTIVE_REASON_TO_UPSTREAM.get(reason)
    payload_stub = {
        "monitored_price": None,
        "discrepancies": [],
        "lowest_competitor": None,
        "highest_competitor": None,
        "reason": reason,
        "upstream_reason": resolved_upstream,
        "ignored_due_to_inactive": True,
    }
    now = datetime.now(timezone.utc)
    comparison = create_price_comparison(
        db,
        monitored.id,
        payload_stub,
        competitors_with_price_count=0,
        completed_at=now,
    )
    summary_payload = apply_summary_defaults(
        payload_stub,
        timestamp=comparison.timestamp,
        comparison_id=comparison.id,
        competitors_count=total,
    )
    summary_payload["competitors_with_price_count"] = 0
    summary_payload["competitiveness_status"] = None
    summary_payload["comparison_insights"] = None
    summary_payload["ignored_due_to_inactive"] = True
    if resolved_upstream:
        summary_payload["upstream_reason"] = resolved_upstream
    encoded_summary = jsonable_encoder(summary_payload)
    upsert_price_comparison_summary(db, monitored.id, comparison.id, encoded_summary)
    return {
        "summary": encoded_summary,
        "comparison_id": str(comparison.id),
        "monitored_id": str(monitored.id),
        "user_id": str(monitored.user_id),
        "lowest_competitor": None,
        "highest_competitor": None,
    }

def _persist_comparison_result(
    db: Session,
    *,
    monitored: Any,
    result: Dict[str, Any],
    total: int,
    available: List[CompetitorProduct],
) -> Dict[str, Any]:
    """ Persiste comparação e devolve payload final normalizado para os consumidores """
    persist_raw_result = getattr(settings, "COMPARISON_STORE_RAW_RESULT", False)
    stored_payload = (
        result
        if persist_raw_result
        else {
            "monitored_price": result.get("monitored_price"),
            "discrepancies": result.get("discrepancies", []),
            "lowest_competitor": result.get("lowest_competitor"),
            "highest_competitor": result.get("highest_competitor"),
        }
    )

    now = datetime.now(timezone.utc)
    competitors_with_price = len(available)
    comparison = create_price_comparison(
        db,
        monitored.id,
        stored_payload,
        competitors_with_price_count=competitors_with_price,
        completed_at=now,
    )
    summary_payload = apply_summary_defaults(
        compute_summary_from_payload(
            result,
            timestamp=comparison.timestamp,
            comparison_id=comparison.id,
            competitors_count=total,
        ),
        timestamp=comparison.timestamp,
        comparison_id=comparison.id,
        competitors_count=total,
    )
    encoded_summary = jsonable_encoder(summary_payload)
    if not available:
        encoded_summary["reason"] = (
            encoded_summary.get("reason") or "no_available_competitors"
        )
    upsert_price_comparison_summary(db, monitored.id, comparison.id, encoded_summary)

    result["summary"] = encoded_summary
    result["comparison_id"] = str(comparison.id)
    result["monitored_id"] = str(monitored.id)
    result["user_id"] = str(monitored.user_id)
    return result

def _extract_competitors_count_from_summary(
    stored_summary: PriceComparisonSummary | None,
) -> int:
    """ Obtém a contagem de concorrentes a partir dos agregados persistidos """
    if stored_summary is None:
        return 0
    aggregates = (
        stored_summary.aggregates
        if isinstance(stored_summary.aggregates, dict)
        else {}
    )
    try:
        raw_count = aggregates.get("competitors_count")
        if raw_count is None:
            raw_count = aggregates.get("competitors_with_price_count", 0)
        return int(raw_count)
    except (TypeError, ValueError):
        return 0
