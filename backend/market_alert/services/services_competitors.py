""" Serviços de apoio para rotinas de concorrentes monitorados """

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
from market_alert.schemas.schemas_products import CompetitorsListResponse
from market_alert.services.services_products import build_competitor_response
from market_alert.services.services_access import ensure_user_can_access_monitored
from market_alert.services.services_priority_queue import PriorityQueueService
from market_alert.utils.rate_limiter import allow_with_leaky_bucket, parse_rate_limit_config
from market_alert.utils.interval_calculator_products import calculate_next_check_at
from market_alert.core.config_alert import settings

from shared.utils.url_validation import normalize_and_validate_product_url
from shared import metrics
from shared.metrics.metrics_products import (
    COMPETITOR_DELETED_TOTAL,
    COMPETITOR_DELETE_FAILURES_TOTAL,
)
from market_alert.core.celery_app import celery_app


logger = structlog.get_logger(__name__)

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

def validate_competitor_limit(
    *,
    db: Session,
    monitored_product_id: UUID,
    limit: int,
    count_competitors_callback,
    context: dict[str, str] | None = None,
) -> None:
    """ Garante que o monitorado respeita o limite máximo de concorrentes """
    log_context = {"monitored_id": str(monitored_product_id), "limit": limit}
    if context:
        log_context.update(context)

    competitors_total = count_competitors_callback(db, monitored_product_id, include_paused=True)

    if competitors_total >= limit:
        logger.warning("competitor_limit_reached", **log_context)
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Limite de concorrentes atingido para este produto monitorado.",
        )
    
def enforce_competitor_scrape_rate_limit(user_id: UUID) -> None:
    """ Garante que requisições de scraping respeitam limites configurados por usuário."""
    parsed_limit = parse_rate_limit_config(settings.COMPETITOR_RATE_LIMIT)
    if not parsed_limit:
        return

    max_requests, window_seconds = parsed_limit
    bucket_key = f"rate:competitor:{user_id}"

    allowed = allow_with_leaky_bucket(
        bucket_key,
        rate_limit=parsed_limit,
    )

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

    monitored_is_paused = bool(monitored_product.paused)

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

    validate_competitor_limit(
        db=db,
        monitored_product_id=monitored_product.id,
        limit=settings.MAX_COMPETITORS_PER_MONITORED,
        count_competitors_callback=count_competitors_by_monitored,
        context=context,
    )

    enforce_competitor_scrape_rate_limit(user.id)

    pending = create_pending_competitor_product(
        db=db,
        monitored_product_id=monitored_product.id,
        product_url=normalized_url,
        display_name=product_data.name,
        is_paused=monitored_is_paused,
    )

    metrics.PENDING_COMPETITOR_CREATED_TOTAL.inc()
    logger.info(
        "pending_competitor_created",
        competitor_id=str(pending.id),
        monitored_id=str(monitored_product.id),
        status=pending.status.value,
        **context,
    )

    if monitored_is_paused:
        #Mantém o concorrente sincronizado ao estado pausado do monitorado
        logger.info(
            "competitor_created_while_monitored_paused",
            competitor_id=str(pending.id),
            monitored_id=str(monitored_product.id),
            **context,
        )
    else:
        #Garante que o monitorado estará em fila para coletar o novo concorrente no próximo ciclo
        queue_service = PriorityQueueService()
        score = queue_service.get_score(str(monitored_product.id))
        if score is None:
            #Recalcula janela para garantir entrada do monitorado em fila única
            reference_time = datetime.now(timezone.utc)
            monitored_product.next_check_at = calculate_next_check_at(
                monitored_product,
                collected_at=reference_time,
            )
            db.commit()
            db.refresh(monitored_product)

            enqueued = queue_service.enqueue(
                str(monitored_product.id),
                monitored_product.next_check_at,
            )
            if enqueued:
                queue_service.set_enqueued_at(str(monitored_product.id), reference_time)
                logger.info(
                    "monitored_enqueued_to_priority_queue",
                    monitored_id=str(monitored_product.id),
                    source="competitor_create",
                )
            else:
                #Não bloqueia criação quando Redis estiver indisponível
                logger.warning(
                    "monitored_priority_queue_enqueue_failed",
                    monitored_id=str(monitored_product.id),
                    source="competitor_create",
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

def list_competitors_with_pagination(
    *,
    db: Session,
    user: User,
    monitored_product_id: UUID,
    page: int,
    per_page: int,
    include_inactive: bool,
    include_paused: bool,
    context: dict[str, str] | None = None,
) -> CompetitorsListResponse:
    """ Coordena validação de acesso, filtros e paginação de concorrentes """
    ensure_user_can_access_monitored(
        db=db,
        product_id=monitored_product_id,
        user=user,
        context=context,
        hide_forbidden=False,
    )

    total, with_price_count, excluded_count, competitors = paginate_competitors(
        db,
        monitored_product_id,
        page=page,
        per_page=per_page,
        include_inactive=include_inactive,
        include_paused=include_paused,
    )

    items: list = []
    for competitor in competitors:
        try:
            items.append(build_competitor_response(competitor, allow_missing_price=True))
        except HTTPException as exc:
            # Ignora concorrentes incompletos preservando previsibilidade da listagem
            logger.warning(
                "competitor_without_price",
                competitor_id=str(competitor.id),
                monitored_id=str(monitored_product_id),
                status=competitor.status.value,
                detail=str(exc.detail),
                **(context or {}),
            )
            continue

    return CompetitorsListResponse(
        items=items,
        competitors_total=total,
        competitors_with_price_count=with_price_count,
        excluded_due_to_inactive_count=excluded_count,
        page=page,
        per_page=per_page,
    )

def delete_competitor_entry(
    *,
    db: Session,
    competitor_id: UUID,
    user: User,
    context: dict[str, str] | None = None,
) -> UUID:
    """ Remove concorrente com transação, limpeza de históricos e recálculo """
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

        # Evita reabrir transações ativas ao usar o commit explícito
        db.commit()

        #Cascatas de relacionamento cuidam do histórico de preços e dependências
        logger.info(
            "competitor_deleted",
            **log_context,
            monitored_id=str(monitored_id),
        )

        COMPETITOR_DELETED_TOTAL.inc()
        #Enfileira recálculo via Celery sem importar a task diretamente para evitar ciclo
        celery_app.send_task(
            "market_alert.tasks.compare_prices_task.compare_prices_task",
            args=[str(monitored_id)],
            queue="monitor",
        )
        logger.info(
            "competitor_delete_recalculation_enqueued",
            monitored_id=str(monitored_id),
            competitor_id=str(competitor_id),
        )
        return monitored_id
    except HTTPException:
        db.rollback()
        COMPETITOR_DELETE_FAILURES_TOTAL.inc()
        raise
    except Exception as exc:
        db.rollback()
        COMPETITOR_DELETE_FAILURES_TOTAL.inc()
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
) -> list[CompetitorProduct]:
    """ Apaga todos os concorrentes vinculados ao monitorado do usuário """
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
    
    return delete_competitors_by_monitored_id(db, monitored_product_id)
