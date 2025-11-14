""" Rotas para consulta de comparações de preços """

import structlog
from fastapi import APIRouter, Body, Depends, Header, HTTPException, Request, status
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
from typing import List
from uuid import UUID

from shared.infra.db import get_db
from market_alert.models import User
from market_alert.schemas.schemas_comparisons import (
    PriceComparisonResponse,
    PriceComparisonSummaryResponse,
    PriceComparisonRunRequest,
)
from market_alert.core.security import get_current_user
from market_alert.crud.crud_monitored import get_monitored_product_by_id
from market_alert.crud.crud_comparison import (
    get_latest_comparisons,
    get_comparison_by_id,
    get_latest_comparisons_for_products,
    get_latest_summary,
)
from market_alert.services.services_comparison import (
    run_price_comparison,
    build_comparison_summary,
)
from backend.shared.infra.redis import (
    IdempotencyOwnershipError,
    register_idempotency_key,
    store_idempotency_response,
)
from market_alert.core.config_alert import settings
from shared.utils.redis_client import consume_leaky_bucket


router = APIRouter(prefix="/comparisons", tags=["Comparações"])
logger = structlog.get_logger("http_route")

def _parse_rate_limit_config(rate_limit: str) -> tuple[int, int] | None:
    """Converte configuração textual em ``(capacidade, janela_em_segundos)``."""

    cleaned = (rate_limit or "").strip()
    if not cleaned or "/" not in cleaned:
        return None

    amount_part, window_part = cleaned.split("/", 1)
    try:
        max_requests = int(amount_part)
    except ValueError:
        logger.warning("manual_comparison_invalid_rate_limit", raw=rate_limit)
        return None

    unit = window_part.strip().lower()
    unit_mapping = {
        "s": 1,
        "sec": 1,
        "secs": 1,
        "second": 1,
        "seconds": 1,
        "m": 60,
        "min": 60,
        "mins": 60,
        "minute": 60,
        "minutes": 60,
        "h": 3600,
        "hour": 3600,
        "hours": 3600,
    }

    if unit.isdigit():
        window_seconds = int(unit)
    else:
        window_seconds = unit_mapping.get(unit)

    if not window_seconds or max_requests <= 0:
        logger.warning("manual_comparison_rate_limit_invalid_window", raw=rate_limit)
        return None

    return max_requests, window_seconds


def _enforce_manual_comparison_rate_limit(user_id: UUID) -> None:
    """Aplica o rate limit do tipo *leaky bucket* para execuções manuais."""

    parsed_limit = _parse_rate_limit_config(settings.MANUAL_COMPARISON_RATE_LIMIT)
    if not parsed_limit:
        return

    max_requests, window_seconds = parsed_limit
    leak_rate = max_requests / window_seconds
    bucket_key = f"rate:comparison_manual:{user_id}"

    allowed, _ = consume_leaky_bucket(
        bucket_key,
        capacity=max_requests,
        leak_rate_per_second=leak_rate,
    )

    if not allowed:
        logger.warning(
            "manual_comparison_rate_limit_exceeded",
            user_id=str(user_id),
            limit=max_requests,
            window=window_seconds,
        )
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Limite de comparações manuais atingido. Aguarde alguns instantes.",
        )

@router.get("/{monitored_id}", response_model=List[PriceComparisonResponse])
def list_comparisons(request: Request, monitored_id: UUID, limit: int = 10, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """ Lista as comparações recentes de um produto monitorado. """
    logger.info("route_called", path=request.url.path, method=request.method, user_id=str(user.id), monitored_id=str(monitored_id))

    mp = get_monitored_product_by_id(db, monitored_id)
    if not mp or mp.user_id != user.id:
        logger.warning("route_error", path=request.url.path, method=request.method, reason="not_found", monitored_id=str(monitored_id))
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Produto monitorado não encontrado.")

    comparisons = get_latest_comparisons(db, monitored_id, limit)
    logger.info("route_completed", path=request.url.path, method=request.method, status="success", count=len(comparisons))
    return comparisons

@router.get("/{monitored_id}/summary", response_model=PriceComparisonSummaryResponse)
def get_comparison_summary(request: Request, monitored_id: UUID, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """ Retorna o resumo agregado da última comparação executada para o produto monitorado """
    logger.info("route_called", path=request.url.path, method=request.method, user_id=str(user.id), monitored_id=str(monitored_id))

    mp = get_monitored_product_by_id(db, monitored_id)
    if not mp or mp.user_id != user.id:
        logger.warning("route_error", path=request.url.path, method=request.method, reason="not_found", monitored_id=str(monitored_id))
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Produto monitorado não encontrado.")
    
    latest_comparison = get_latest_comparisons_for_products(db, [monitored_id]).get(monitored_id)
    stored_summary = get_latest_summary(db, monitored_id)
    competitors_count = len(getattr(mp, "competitors", []) or [])
    summary = build_comparison_summary(
        latest_comparison,
        competitors_count=competitors_count,
        stored_summary=stored_summary,
    )

    logger.info("route_completed", path=request.url.path, method=request.method, status="success", monitored_id=str(monitored_id))
    return PriceComparisonSummaryResponse(
        monitored_product_id=monitored_id,
        **summary,
    )

@router.get("/detail/{comparison_id}", response_model=PriceComparisonResponse)
def get_comparison(request: Request, comparison_id: UUID, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """ Obtém os detalhes de uma comparação específica """
    logger.info("route_called", path=request.url.path, method=request.method, user_id=str(user.id), comparison_id=str(comparison_id))

    comparison = get_comparison_by_id(db, comparison_id)
    if not comparison:
        logger.warning("route_error", path=request.url.path, method=request.method, reason="not_found", comparison_id=str(comparison_id))
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Comparação não encontrada.")

    mp = get_monitored_product_by_id(db, comparison.monitored_product_id)
    if not mp or mp.user_id != user.id:
        logger.warning("route_error", path=request.url.path, method=request.method, reason="not_found", monitored_id=str(comparison.monitored_product_id))
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Produto monitorado não encontrado.")

    logger.info("route_completed", path=request.url.path, method=request.method, reason="success", comparison_id=str(comparison_id))
    return comparison

@router.post("/{monitored_id}/run", response_model=dict)
def run_comparison_endpoint(
    request: Request,
    monitored_id: UUID,
    payload: PriceComparisonRunRequest | None = Body(default=None),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user)
):
    """ Executa nova comparação de preços com suporte a tolerâncias personalizdas e idempotência

    O payload opcional aceita ``tolerance`` e ``price_change_threshold`` enquanto o header
    ``Idempotency-Key`` permite que o cliente evite disparos duplicados. O retorno mantém
    o mesmo formato de comparação persistida, com agregados a alertas utilizados pelo frontend.
    """
    logger.info("route_called", path=request.url.path, method=request.method, user_id=str(user.id), monitored_id=str(monitored_id), idempotency_key=idempotency_key)

    mp = get_monitored_product_by_id(db, monitored_id)
    if not mp or mp.user_id != user.id:
        logger.warning("route_error", path=request.url.path, method=request.method, reason="not_found", monitored_id=str(monitored_id))
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Produto monitorado não encontrado.")

    tolerance = payload.tolerance if payload is not None else None
    price_change_threshold = (
        payload.price_change_threshold if payload is not None else None
    )

    owner_reference = str(user.id)

    try:
        idempotency_record = register_idempotency_key(
            namespace="comparison_run",
            key=idempotency_key,
            owner=owner_reference,
            ttl_seconds=settings.IDEMPOTENCY_TTL_SECONDS,
        )
    except IdempotencyOwnershipError as exc:
        logger.warning("idempotency_conflict", path=request.url.path, method=request.method, key=idempotency_key)
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Chave de idempotência já utilizada por outro usuário",
        ) from exc
    
    if idempotency_record and not idempotency_record.is_new:
        logger.info("idempotency_replayed", path=request.url.path, method=request.method, key=idempotency_key)
        if idempotency_record.response is not None:
            return JSONResponse(
                content=idempotency_record.response,
                status_code=idempotency_record.status_code or status.HTTP_200_OK,
            )
        return JSONResponse(
            content={"message": "Comparação já está em processamento."},
            status_code=status.HTTP_202_ACCEPTED,
        )
    
    try:
        _enforce_manual_comparison_rate_limit(user.id)
    except HTTPException as exc:
        error_payload = exc.detail if isinstance(exc.detail, dict) else {"detail": str(exc.detail)}
        if idempotency_record:
            store_idempotency_response(
                namespace="comparison_run",
                key=idempotency_key,
                owner=owner_reference,
                ttl_seconds=settings.IDEMPOTENCY_TTL_SECONDS,
                response=error_payload,
                status_code=exc.status_code,
            )
        raise

    result, alerts = run_price_comparison(
        db,
        monitored_id,
        tolerance=tolerance,
        price_change_threshold=price_change_threshold,
    )
    logger.info("route_completed", path=request.url.path, method=request.method, status="success", alerts=len(alerts))

    if idempotency_record:
        store_idempotency_response(
            namespace="comparison_run",
            key=idempotency_key,
            owner=owner_reference,
            ttl_seconds=settings.IDEMPOTENCY_TTL_SECONDS,
            response=result,
            status_code=status.HTTP_200_OK,
        )
    return result
