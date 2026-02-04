""" Camada de serviço para criação, listagem e agendar monitorados """

from __future__ import annotations

from datetime import datetime, timezone
from fastapi import HTTPException, Request, status
from sqlalchemy.orm import Session
import structlog
from uuid import UUID, uuid4

from backend.shared.schemas.shared_schemas_products import (
    MonitoredProductCreateScraping,
    CompetitorProductCreateScraping,
)
from shared.utils.url_validation import normalize_and_validate_product_url

from market_alert.core.config_alert import settings
from market_alert.crud.crud_monitored import (
    create_pending_monitored_product,
    get_monitored_product_by_user_and_url,
    get_all_monitored_products,
    get_featured_monitored_products,
    get_monitored_product_by_id,
    delete_monitored,
    get_last_price_change_for_monitored,
    pause_monitored,
    resume_monitored,
    MonitoredLockError,
    MonitoredNotFoundError,
    MonitoredOwnershipError,
)
from market_alert.crud.crud_comparison import (
    get_latest_summaries_for_products,
    get_latest_summary,
)
from market_alert.models import MonitoredProduct, User
from market_alert.schemas.schemas_products import (
    MonitoredPausedUpdateRequest,
    MonitoredProductResponse,
    MonitoredScrapeCreationResponse,
    PaginatedMonitoredProductsResponse,
    PaginationMeta,
)
from market_alert.enums.enums_comparisons import CompetitivenessStatus
from market_alert.services.services_products import build_monitored_response
from market_alert.services.services_competitors import create_competitor_scrape_request
from market_alert.services.services_priority_queue_manager import enqueue_monitored_now
from market_alert.orchestrator.collector_service_orchestrator import build_monitored_payload, enqueue_collect
from market_alert.utils.rate_limiter import allow_with_leaky_bucket, parse_rate_limit_config
from market_alert.utils.interval_calculator_products import calculate_next_check_at


logger = structlog.get_logger("monitored_service")

def _enqueue_resume_collection(monitored: MonitoredProduct, user: User) -> None:
    """ Agenda coleta imediata com comparação forçada para retomadas """
    payload = build_monitored_payload(
        monitored,
        user_id=user.id,
        trace_id=str(uuid4()),
    )
    payload["force_compare"] = "true"
    try:
        enqueue_collect(payload)
    except Exception:
        #Evita bloquear a retomada caso a fila de scraping esteja indisponível
        logger.warning(
            "monitored_resume_collect_enqueue_failed",
            monitored_id=str(monitored.id),
            user_id=str(user.id),
        )

def _raise_from_monitored_error(exc: Exception) -> None:
    """ Converte exceções de domínio em respostas HTTP coerentes """
    if isinstance(exc, MonitoredNotFoundError):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Produto não encontrado.",
        ) from exc
    if isinstance(exc, MonitoredOwnershipError):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Operação não permitida para este usuário.",
        ) from exc
    if isinstance(exc, MonitoredLockError):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Monitorado em processamento, tente novamente em instantes.",
        ) from exc
    raise exc

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

    A função mantém a lógica de obtenção de resumos mais recentes e montagem
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
        response_payload.append(
            build_monitored_response(
                product,
                summary=summaries_map.get(product.id),
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

    A função centraliza a obtenção dos resumos e aplica o mesmo tratamento de
    itens sem preço para evitar respostas inconsistentes.
    """
    featured_items = get_featured_monitored_products(
        db,
        user_id,
        limit=limit,
    )

    summary_map = get_latest_summaries_for_products(
        db, [product.id for product in featured_items]
    )

    response_payload: list[MonitoredProductResponse] = []
    for product in featured_items:
        try:
            response_payload.append(
                build_monitored_response(
                    product, summary=summary_map.get(product.id)
                )
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

    summary = get_latest_summary(db, product_id)
    last_price_change_at = get_last_price_change_for_monitored(db, product_id)

    return build_monitored_response(
        product,
        summary=summary,
        allow_missing_price=True,
        last_price_change_at=last_price_change_at,
        global_last_price_change_at=last_price_change_at,
    )


def pause_monitored_product_entry(
    *, db: Session, product_id: UUID, user: User
) -> MonitoredProductResponse:
    """ Pausa monitorado, remove da fila e devolve estado atualizado """
    try:
        monitored = pause_monitored(db, product_id, user)
    except Exception as exc:
        _raise_from_monitored_error(exc)
    #Recarrega estado canônico do banco antes de montar o DTO
    refreshed = get_monitored_product_by_id(db, product_id)
    if refreshed is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Produto não encontrado")

    logger.info("monitored_paused", product_id=str(product_id), user_id=str(user.id))
    summary = get_latest_summary(db, product_id)
    return build_monitored_response(
        refreshed,
        summary=summary,
        allow_missing_price=True,
    )

def resume_monitored_product_entry(
    *, db: Session, product_id: UUID, user: User
) -> MonitoredProductResponse:
    """ Retoma monitorado, recalcula janela e reinsere na fila """
    try:
        monitored = resume_monitored(db, product_id, user)
    except Exception as exc:  # noqa: BLE001 - conversão controlada para HTTP
        _raise_from_monitored_error(exc)
    #Recarrega estado canônico do banco antes de montar o DTO
    refreshed = get_monitored_product_by_id(db, product_id)
    if refreshed is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Produto não encontrado")

    logger.info("monitored_resumed", product_id=str(product_id), user_id=str(user.id))
    _enqueue_resume_collection(monitored, user)
    summary = get_latest_summary(db, product_id)
    last_price_change_at = get_last_price_change_for_monitored(db, product_id)
    return build_monitored_response(
        refreshed,
        summary=summary,
        allow_missing_price=True,
        last_price_change_at=last_price_change_at,
        global_last_price_change_at=last_price_change_at,
    )

def update_monitored_pause_state(
    *, db: Session, product_id: UUID, user: User, payload: MonitoredPausedUpdateRequest
) -> MonitoredProductResponse:
    """ Ajusta a pausa, sincroniza fila de prioridade e devolve o estado consolidado """
    try:
        monitored = (
            pause_monitored(db, product_id, user)
            if payload.paused
            else resume_monitored(db, product_id, user)
        )
    except Exception as exc:
        _raise_from_monitored_error(exc)
    #Garante que retornamos o estado canônico recarregado do banco
    refreshed = get_monitored_product_by_id(db, product_id)
    if refreshed is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Produto não encontrado")

    action = "paused" if payload.paused else "resumed"
    logger.info(f"monitored_{action}", product_id=str(product_id), user_id=str(user.id))
    if not payload.paused:
        _enqueue_resume_collection(monitored, user)

    summary = get_latest_summary(db, product_id)
    last_price_change_at = get_last_price_change_for_monitored(db, product_id)
    return build_monitored_response(
        refreshed,
        summary=summary,
        allow_missing_price=True,
        last_price_change_at=last_price_change_at,
        global_last_price_change_at=last_price_change_at,
    )

def delete_monitored_product_entry(
    *, db: Session, product_id: UUID, user: User
) -> None:
    """ Remove monitorado aplicando lock e sem payload de resposta """
    try:
        delete_monitored(db, product_id, user)
    except Exception as exc:
        _raise_from_monitored_error(exc)

def schedule_monitored_scrape(
    *,
    db: Session,
    user: User,
    product_data: MonitoredProductCreateScraping,
    request: Request | None = None,
) -> MonitoredScrapeCreationResponse:
    """ Valida, cria monitorado e enfileira coleta imediata na fila continua.
    
    O serviço centraliza logs e validações para reduzir duplicação entre rotas,
    garantindo verificação de URL, duplicidade e rate-limit antes de agendar a
    coleta assíncrona do monitorado, mantendo o registro na fila de prioridade
    para rechecagens contínuas. Quando enviado, também cria o concorrente
    inicial.
    """
    log_context: dict[str, str | None] = {
        "user_id": str(user.id),
        "path": request.url.path if request else None,
        "method": request.method if request else None,
        "monitoring_type": "scraping",
    }
    logger.info(
        "monitored_scrape_requested",
        **{key: value for key, value in log_context.items() if value is not None},
    )

    try:
        normalized_url, issue = normalize_and_validate_product_url(
            str(product_data.product_url)
        )
    except ValueError as exc:
        logger.warning(
            "monitored_invalid_url", url=str(product_data.product_url), error=str(exc)
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc

    if issue:
        logger.warning("monitored_invalid_url", url=normalized_url, code=issue.code)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=issue.message
        )
    
    existing = get_monitored_product_by_user_and_url(db, user.id, normalized_url)

    if existing:
        if (
            product_data.name_identification
            and existing.name_identification != product_data.name_identification
        ):
            #Atualiza a identificação para refletir a escolha mais recente do usuário
            existing.name_identification = product_data.name_identification
            db.commit()
            db.refresh(existing)

        logger.info("monitored_already_exists", monitored_id=str(existing.id))
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Este produto já está sendo monitorado.",
        )
    
    parsed_limit = parse_rate_limit_config(settings.SCRAPER_RATE_LIMIT)
    if parsed_limit:
        max_requests, window_seconds = parsed_limit
        bucket_key = f"rate:scrape:{user.id}"
        allowed = allow_with_leaky_bucket(
            bucket_key,
            rate_limit=parsed_limit,
        )

        if not allowed:
            logger.warning(
                "monitored_rate_limit_exceeded",
                user_id=str(user.id),
                limit=max_requests,
                window=window_seconds,
            )
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Limite de scraping atingido. Tente novamente em instantes.",
            )

    pending = create_pending_monitored_product(
        db=db,
        user_id=user.id,
        name_identification=product_data.name_identification,
        product_url=normalized_url,
    )

    reference_time = datetime.now(timezone.utc)
    pending.next_check_at = calculate_next_check_at(pending, collected_at=reference_time)
    db.commit()
    db.refresh(pending)

    try:
        #Dispara coleta imediata na fila scraping para devolver resposta incial rapidamente
        immediate_trace_id = str(uuid4())
        immediate_payload = build_monitored_payload(
            pending,
            user_id=user.id,
            trace_id=immediate_trace_id,
        )
        enqueue_collect(immediate_payload)
        logger.info(
            "monitored_immediate_enqueued",
            monitored_id=str(pending.id),
            trace_id=immediate_trace_id,
        )
        #Mantém monitorado na fila contínua para rechecagens subsequentes
        enqueued = enqueue_monitored_now(pending.id, source="new_monitored")
        if not enqueued:
            logger.warning(
                "monitored_enqueue_failed_fallback",
                monitored_id=str(pending.id),
                reason="priority_queue_unavailable",
            )
    except Exception:
        #Evita bloquear a criação quando Redis estiver indisponível
        logger.warning(
            "monitored_enqueue_exception_fallback",
            monitored_id=str(pending.id),
            exc_info=True,
        )

    competitor_warning: str | None = None
    if product_data.initial_competitor:
        competitor_payload = CompetitorProductCreateScraping(
            monitored_product_id=pending.id,
            product_url=product_data.initial_competitor.product_url,
            name=product_data.initial_competitor.name,
        )
        competitor_context = {
            "path": request.url.path if request else None,
            "method": request.method if request else None,
            "origin": "monitored_onboarding",
        }

        try:
            create_competitor_scrape_request(
                db=db,
                user=user,
                product_data=competitor_payload,
                request_context={
                    key: value for key, value in competitor_context.items() if value is not None
                },
            )
        except HTTPException as exc:
            #Comentário preserva o monitorado criado, mas informa o alerta do concorrente inicial
            competitor_warning = str(exc.detail)
            logger.warning(
                "monitored_initial_competitor_failed",
                monitored_id=str(pending.id),
                detail=competitor_warning,
            )

    logger.info(
        "monitored_scrape_scheduled",
        monitored_id=str(pending.id),
        url=normalized_url,
        next_check_at=pending.next_check_at,
    )

    return MonitoredScrapeCreationResponse(
        id=pending.id,
        url=pending.normalized_url,
        created_at=pending.created_at,
        next_check_at=pending.next_check_at,
        message="Coleta iniciada, dados aparecerão em breve.",
        competitor_warning=competitor_warning,
    )
