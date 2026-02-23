""" Operações de ciclo de vida para produtos concorrentes.

Responsabilidade única: criar, pausar e deletar concorrentes.

Fluxo de dependências:
    Routes → este service → CRUD (persistência)
    Routes → este service → Orchestrator (enfileiramento Celery)
    Routes → este service → Orchestrator (fila Redis via CollectionQueue)

NÃO conhece: comparações, notificações, dashboards, rate limiting de monitorados.

Exemplo de uso em uma route:
    from market_alert.services.services_competitor_lifecycle import (
        create_competitor_scrape_request,
        delete_competitor_entry,
    )
"""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

import structlog
from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from backend.shared.schemas.shared_schemas_products import CompetitorProductCreateScraping
from market_alert.models import User
from market_alert.models.models_products import CompetitorProduct
from market_alert.crud.crud_competitor import (
    count_competitors_by_monitored,
    create_pending_competitor_product,
    get_competitor_by_monitored_and_url,
    get_competitor_by_id,
    paginate_competitors,
    delete_competitor,
    delete_competitors_by_monitored_id,
)
from market_alert.schemas.schemas_products import CompetitorScrapeCreationResponse
from market_alert.services.services_products import build_competitor_response
from market_alert.services.services_access import ensure_user_can_access_monitored
from market_alert.orchestrator.collection_queue import CollectionQueue
from market_alert.orchestrator.collector_service_orchestrator import enqueue_competitor_collection
from market_alert.utils.rate_limiter import allow_with_leaky_bucket, parse_rate_limit_config
from market_alert.domain.product_lifecycle import compute_next_check_at
from market_alert.utils.interval_calculator_products import EVENT_STANDARD
from market_alert.core.config_alert import settings
from market_alert.utils.price_comparator import request_comparison_recompute

from shared.utils.url_validation import normalize_and_validate_product_url


logger = structlog.get_logger(__name__)

# ---------------------------------------------------------------------------
# Helpers internos
# ---------------------------------------------------------------------------

def _ensure_competitor_access(
    *,
    db: Session,
    competitor_id: UUID,
    user: User,
    context: dict[str, str] | None = None,
) -> CompetitorProduct:
    """ Valida se o concorrente pertence ao usuário autenticado """
    log_context: dict[str, str] = {
        "competitor_id": str(competitor_id),
        "user_id": str(user.id),
    }
    if context:
        log_context.update(context)

    competitor = get_competitor_by_id(db, competitor_id)
    if competitor is None:
        logger.warning("competitor_not_found", **log_context)
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Concorrente não encontrado.",
        )

    owner_id = competitor.monitored_product.user_id if competitor.monitored_product else None
    if owner_id != user.id:
        log_context["owner_id"] = str(owner_id)
        logger.warning("competitor_forbidden", **log_context)
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Usuário não possui permissão para remover este concorrente.",
        )

    return competitor

def _validate_competitor_limit(
    *,
    db: Session,
    monitored_product_id: UUID,
    limit: int,
    context: dict[str, str] | None = None,
) -> None:
    """ Garante que o monitorado respeita o limite máximo de concorrentes """
    log_context = {"monitored_id": str(monitored_product_id), "limit": limit}
    if context:
        log_context.update(context)

    competitors_total = count_competitors_by_monitored(db, monitored_product_id, include_paused=True)
    if competitors_total >= limit:
        logger.warning("competitor_limit_reached", **log_context)
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Limite de concorrentes atingido para este produto monitorado.",
        )

def _enforce_competitor_scrape_rate_limit(user_id: UUID) -> None:
    """ Garante que requisições de scraping respeitam limites configurados por usuário """
    parsed_limit = parse_rate_limit_config(settings.COMPETITOR_RATE_LIMIT)
    if not parsed_limit:
        return

    max_requests, window_seconds = parsed_limit
    bucket_key = f"rate:competitor:{user_id}"

    allowed = allow_with_leaky_bucket(bucket_key, rate_limit=parsed_limit)
    if not allowed:
        logger.warning(
            "competitor_rate_limit_exceeded",
            user_id=str(user_id),
            limit=max_requests,
            window=window_seconds,
        )
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Limite de scraping de concorrentes atingido. Tente novamente em instantes.",
        )


# ---------------------------------------------------------------------------
# Operações públicas de ciclo de vida
# ---------------------------------------------------------------------------

def create_competitor_scrape_request(
    *,
    db: Session,
    user: User,
    product_data: CompetitorProductCreateScraping,
    request_context: dict[str, str] | None = None,
) -> CompetitorScrapeCreationResponse:
    """ Orquestra validações, criação e agendamento conjunto do concorrente """
    context = request_context or {}
    log_context = {
        "user_id": str(user.id),
        "monitored_id": str(product_data.monitored_product_id),
        **context,
    }

    logger.info("competitor_scrape_request_received", **log_context)

    try:
        normalized_url, issue = normalize_and_validate_product_url(str(product_data.product_url))
    except ValueError as exc:
        logger.warning("invalid_competitor_url", url=str(product_data.product_url), error=str(exc), **context)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))

    if issue:
        logger.warning("invalid_competitor_url", url=normalized_url, code=issue.code, **context)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=issue.message)

    monitored_product = ensure_user_can_access_monitored(
        db=db,
        product_id=product_data.monitored_product_id,
        user=user,
        context=context,
        hide_forbidden=False,
    )

    if normalized_url == monitored_product.normalized_url:
        # Evita concorrente auto-referenciado no monitorado
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="URL do concorrente não pode ser igual ao monitorado.",
        )

    monitored_is_paused = bool(monitored_product.paused)

    if monitored_is_paused:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Monitoramento pausado. Retome o produto para adicionar concorrentes.",
        )

    existing = get_competitor_by_monitored_and_url(db, monitored_product.id, normalized_url)
    if existing:
        logger.info(
            "competitor_exists",
            monitored_id=str(monitored_product.id),
            competitor_id=str(existing.id),
            **context,
        )
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Concorrente já cadastrado para este produto monitorado.",
        )

    _validate_competitor_limit(
        db=db,
        monitored_product_id=monitored_product.id,
        limit=settings.MAX_COMPETITORS_PER_MONITORED,
        context=context,
    )

    _enforce_competitor_scrape_rate_limit(user.id)

    pending = create_pending_competitor_product(
        db=db,
        monitored_product_id=monitored_product.id,
        product_url=normalized_url,
        display_name=product_data.name,
        is_paused=False,
    )

    logger.info(
        "pending_competitor_created",
        competitor_id=str(pending.id),
        monitored_id=str(monitored_product.id),
        status=pending.status.value,
        **context,
    )

    #Garante que o monitorado está na fila de prioridade para coletar o novo concorrente no próximo ciclo.
    reference_time = datetime.now(timezone.utc)
    #Atualiza estabilidade e próximo agendamento de forma atômica para evitar inconsistência entre score e janela de coleta.
    schedule = compute_next_check_at(
        monitored_product,
        reference_time=reference_time,
        event_type=EVENT_STANDARD,
    )
    monitored_product.stability_score = schedule.stability_score
    monitored_product.next_check_at = schedule.next_check_at
    db.commit()
    db.refresh(monitored_product)

    enqueued = CollectionQueue().enqueue_for_collection(
        monitored_product.id,
        monitored_product.next_check_at,
        source="competitor_create",
    )
    if not enqueued:
        #Não bloqueia criação quando Redis estiver indisponível
        logger.warning(
            "monitored_priority_queue_enqueue_failed",
            monitored_id=str(monitored_product.id),
            source="competitor_create",
        )

    try:
        #Dispara coleta inicial do concorrente para evitar longas filas de pendência
        enqueue_competitor_collection(
            pending,
            user_id=monitored_product.user_id,
            trace_id=context.get("trace_id"),
        )
    except Exception:
        #Não bloqueia o fluxo principal caso a fila de scraping esteja indisponível
        logger.exception(
            "competitor_initial_enqueue_failed",
            competitor_id=str(pending.id),
            monitored_id=str(monitored_product.id),
            **context,
        )

    logger.info(
        "competitor_scrape_scheduled",
        competitor_id=str(pending.id),
        monitored_id=str(monitored_product.id),
        **context,
    )

    return CompetitorScrapeCreationResponse(
        id=pending.id,
        url=pending.product_url,
        created_at=pending.created_at,
        message="Concorrente criado. A coleta ocorrerá no próximo ciclo de monitoramento.",
    )

def delete_competitor_entry(
    *,
    db: Session,
    competitor_id: UUID,
    user: User,
    context: dict[str, str] | None = None,
) -> UUID:
    """ Remove concorrente com transação, limpeza de fila e recálculo de comparação """
    log_context: dict[str, str] = {
        "competitor_id": str(competitor_id),
        "user_id": str(user.id),
    }
    if context:
        log_context.update(context)

    logger.info("competitor_delete_requested", **log_context)

    try:
        competitor = _ensure_competitor_access(
            db=db,
            competitor_id=competitor_id,
            user=user,
            context=context,
        )

        if competitor.monitored_product and competitor.monitored_product.paused:
            #Evita remoção de concorrentes enquanto o monitoramento está pausado
            logger.warning(
                "competitor_delete_blocked_monitored_paused",
                monitored_id=str(competitor.monitored_product_id),
                competitor_id=str(competitor.id),
                user_id=str(user.id),
                **(context or {}),
            )
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Monitoramento pausado. Retome o produto para remover concorrentes.",
            )

        monitored_id = competitor.monitored_product_id
        delete_competitor(db, competitor)
        db.commit()

        #Cascatas de relacionamento cuidam do histórico de preços e dependências
        logger.info("competitor_deleted", **log_context, monitored_id=str(monitored_id))

        removed = CollectionQueue().remove_from_collection(competitor_id, source="competitor_delete")
        if not removed:
            #Não bloqueia remoção do banco quando houver falha de Redis
            logger.warning(
                "competitor_priority_queue_remove_failed",
                competitor_id=str(competitor_id),
                reason="competitor_delete",
            )

        request_comparison_recompute(monitored_id, "competitor_deleted")
        logger.info(
            "competitor_delete_recalculation_enqueued",
            monitored_id=str(monitored_id),
            competitor_id=str(competitor_id),
        )
        return monitored_id
    except HTTPException:
        db.rollback()
        raise
    except Exception as exc:
        db.rollback()
        logger.exception("competitor_delete_failed", **log_context)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erro ao remover concorrente.",
        ) from exc

def clear_competitors_from_monitored(
    *,
    db: Session,
    monitored_product_id: UUID,
    user: User,
    context: dict[str, str] | None = None,
) -> list[UUID]:
    """ Apaga todos os concorrentes do monitorado e remove os IDs da fila de prioridade """
    monitored = ensure_user_can_access_monitored(
        db=db,
        product_id=monitored_product_id,
        user=user,
        context=context,
        hide_forbidden=False,
    )

    if monitored.paused:
        #Mantém consistência ao bloquear remoção em monitoramentos pausados
        logger.warning(
            "competitor_bulk_delete_blocked_monitored_paused",
            monitored_id=str(monitored_product_id),
            user_id=str(user.id),
            **(context or {}),
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Monitoramento pausado. Retome o produto para remover concorrentes.",
        )

    deleted_ids = delete_competitors_by_monitored_id(db, monitored_product_id)
    for competitor_id in deleted_ids:
        removed = CollectionQueue().remove_from_collection(competitor_id, source="competitor_delete")
        if not removed:
            #Mantém remoção em banco mesmo quando Redis estiver indisponível
            logger.warning(
                "competitor_priority_queue_remove_failed",
                competitor_id=str(competitor_id),
                reason="competitor_delete",
            )
    return deleted_ids
