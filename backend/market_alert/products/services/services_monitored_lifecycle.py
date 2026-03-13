""" Operações de ciclo de vida para produtos monitorados.

Responsabilidade única: criar, pausar, retomar e deletar monitorados.

Fluxo de dependências:
    Routes → este service → CRUD (persistência) → Domain (decisões de estado)
    Routes → este service → Orchestrator (enfileiramento Celery)

NÃO conhece: comparações, notificações, dashboards, rate limiting de concorrentes.

Exemplo de uso em uma route:
    from market_alert.services.services_monitored_lifecycle import (
        create_monitored_product,
        update_monitored_pause_state,
        delete_monitored_product_entry,
    )
"""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID, uuid4

import structlog
from fastapi import HTTPException, Request, status
from sqlalchemy.orm import Session

from shared.schemas.shared_schemas_products import MonitoredProductCreateScraping, CompetitorProductCreateScraping
from shared.utils.url_validation import normalize_and_validate_product_url
from shared.utils.redis_locks import acquire_product_lock, release_product_lock

from market_alert.core.config_alert import settings
from market_alert.infraestructure.resilience.rate_limiter import allow_with_leaky_bucket, parse_rate_limit_config
from market_alert.models import MonitoredProduct, User
from market_alert.schemas.schemas_products import (
    MonitoredPausedUpdateRequest,
    MonitoredProductResponse,
    MonitoredScrapeCreationResponse,
)
from market_alert.products.crud.crud_monitored import (
    create_pending_monitored_product,
    get_monitored_product_by_user_and_url,
    get_monitored_product_by_id,
    delete_monitored,
    get_last_price_change_for_monitored,
    pause_monitored,
    resume_monitored,
    MonitoredLockError,
    MonitoredNotFoundError,
    MonitoredOwnershipError,
)
from market_alert.comparisons.crud.crud_comparison import get_latest_summary
from market_alert.products.services.services_products import build_monitored_response
from market_alert.collectors.orchestrator.collector_service_orchestrator import enqueue_collect
from market_alert.collectors.orchestrator.payload_builders import build_monitored_payload
from market_alert.products.domain.product_lifecycle import compute_next_check_at
from market_alert.products.utils.interval_calculator_products import EVENT_STANDARD


logger = structlog.get_logger("services_monitored_lifecycle")
_LOCK_TTL_SECONDS = min(settings.PRODUCT_LOCK_TTL_SECONDS, 30)

#Import condicional: protege testes unitários e ambientes sem Temporal disponível
try:
    from market_orchestrator.alert.alert_client import get_temporal_client
    from market_orchestrator.schemas.schemas_workflow import (
        CollectionPolicy,
        ResumeSignalPayload,
        WorkflowInput,
    )
    _TEMPORAL_AVAILABLE = True
except ImportError:
    _TEMPORAL_AVAILABLE = False

# ---------------------------------------------------------------------------
# Helpers internos
# ---------------------------------------------------------------------------

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

def _acquire_monitored_lock(monitored_id: UUID) -> str:
    """ Adquire lock Redis curto para operações destrutivas do monitorado
    
    Mantemos o lock no service para impedir concorrência entre requests sem
    acoplar a infraestrutura Redis à camada CRUD.
    """
    acquired, owner = acquire_product_lock(monitored_id, ttl_seconds=_LOCK_TTL_SECONDS)
    if not acquired:
        raise MonitoredLockError("Não foi possível adquirir lock do monitorado")
    return owner or ""

def _remove_ids_from_priority_queue(product_ids: list[UUID], *, source: str) -> None:
    """ Sinaliza o workflow Temporal para pausar ou encerrar cada monitorado """
    if not _TEMPORAL_AVAILABLE:
        return
    signal_name = "pause" if source == "user_paused" else "delete"
    client = get_temporal_client()
    for pid in product_ids:
        try:
            client.signal_sync(signal_name, str(pid))
        except Exception as exc:
            logger.warning(
                "temporal_signal_failed",
                signal=signal_name,
                monitored_id=str(pid),
                error=str(exc),
            )

def _enqueue_resume_collection(monitored: MonitoredProduct, user: User) -> None:
    """ Agenda coleta imediata com comparação forçada para retomadas """
    payload = build_monitored_payload(
        monitored,
        user_id=user.id,
        trace_id=str(uuid4()),
    )
    payload_forced = payload.model_copy(update={"force_compare": "true"})
    try:
        enqueue_collect(payload_forced)
    except Exception:
        #Evita bloquear a retomada caso a fila de scraping esteja indisponível
        logger.warning(
            "monitored_resume_collect_enqueue_failed",
            monitored_id=str(monitored.id),
            user_id=str(user.id),
        )

    #Registra retomada no workflow durável para manter estado consistente
    if _TEMPORAL_AVAILABLE:
        try:
            get_temporal_client().signal_sync(
                "resume",
                str(monitored.id),
                ResumeSignalPayload(immediate_collect=True),
            )
        except Exception as exc:
            logger.warning(
                "temporal_signal_failed",
                signal="resume",
                monitored_id=str(monitored.id),
                error=str(exc),
            )

def _enqueue_monitored_at_priority_queue(
    monitored: MonitoredProduct,
    *,
    reference: datetime,
    source: str,
) -> None:
    """ Sinaliza o workflow Temporal para retomar o monitorado (sem coleta imediata) """
    if not _TEMPORAL_AVAILABLE:
        return
    try:
        get_temporal_client().signal_sync(
            "resume",
            str(monitored.id),
            ResumeSignalPayload(immediate_collect=False),
        )
    except Exception as exc:
        logger.warning(
            "temporal_signal_failed",
            signal="resume",
            monitored_id=str(monitored.id),
            source=source,
            error=str(exc),
        )

# ---------------------------------------------------------------------------
# Operações públicas de ciclo de vida
# ---------------------------------------------------------------------------

def create_monitored_product(
    *,
    db: Session,
    user: User,
    product_data: MonitoredProductCreateScraping,
    request: Request | None = None,
) -> MonitoredScrapeCreationResponse:
    """ Valida, cria monitorado e enfileira coleta imediata na fila contínua.

    Centraliza logs e validações para reduzir duplicação entre rotas,
    garantindo verificação de URL, duplicidade e rate-limit antes de agendar a
    coleta assíncrona do monitorado, mantendo o registro na fila de prioridade
    para rechecagens contínuas. Quando enviado, também cria o concorrente inicial.
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
    #O service centraliza a decisão de agendamento para manter estabilidade e janela de coleta atualizadas em conjunto.
    pending_schedule = compute_next_check_at(
        pending,
        reference_time=reference_time,
        event_type=EVENT_STANDARD,
    )
    pending.stability_score = pending_schedule.stability_score
    pending.next_check_at = pending_schedule.next_check_at
    db.commit()
    db.refresh(pending)

    try:
        #Dispara coleta imediata na fila scraping para devolver resposta inicial rapidamente
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

        #Inicia workflow durável de rechecagem contínua (não-bloqueante)
        if _TEMPORAL_AVAILABLE:
            try:
                workflow_input = WorkflowInput(
                    monitored_id=str(pending.id),
                    user_id=str(user.id),
                    policy=CollectionPolicy(
                        interval_seconds=getattr(pending, "check_interval", 3600) or 3600,
                    ),
                )
                get_temporal_client().signal_with_start_sync(workflow_input)
            except Exception as exc:
                logger.warning(
                    "temporal_signal_with_start_failed",
                    monitored_id=str(pending.id),
                    error=str(exc),
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
        from market_alert.products.services.services_competitor_lifecycle import create_competitor_scrape_request

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
                    key: value
                    for key, value in competitor_context.items()
                    if value is not None
                },
            )
        except HTTPException as exc:
            #Preserva o monitorado criado, mas informa o alerta do concorrente inicial
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

def pause_monitored_product_entry(
    *, db: Session, product_id: UUID, user: User
) -> MonitoredProductResponse:
    """ Pausa monitorado, remove da fila de prioridade e devolve estado atualizado """
    try:
        pause_monitored(db, product_id, user)
    except Exception as exc:
        _raise_from_monitored_error(exc)

    #Recarrega estado canônico do banco antes de montar o DTO
    refreshed = get_monitored_product_by_id(db, product_id)
    if refreshed is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Produto não encontrado")

    logger.info("monitored_paused", product_id=str(product_id), user_id=str(user.id))
    _remove_ids_from_priority_queue([product_id], source="user_paused")
    summary = get_latest_summary(db, product_id)
    return build_monitored_response(
        refreshed,
        summary=summary,
        allow_missing_price=True,
    )

def resume_monitored_product_entry(
    *, db: Session, product_id: UUID, user: User
) -> MonitoredProductResponse:
    """ Retoma monitorado, recalcula janela, reinsere na fila de prioridade e agenda coleta """
    reference = datetime.now(timezone.utc)
    try:
        monitored = resume_monitored(db, product_id, user)
    except Exception as exc:
        _raise_from_monitored_error(exc)

    #Recarrega estado canônico do banco antes de montar o DTO
    refreshed = get_monitored_product_by_id(db, product_id)
    if refreshed is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Produto não encontrado")

    logger.info("monitored_resumed", product_id=str(product_id), user_id=str(user.id))

    #Reinserção na fila de prioridade (substituiu o enqueue que estava no CRUD)
    _enqueue_monitored_at_priority_queue(monitored, reference=reference, source="user_resumed")
    #Disparo de coleta imediata com comparação forçada
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
    reference = datetime.now(timezone.utc)
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

    if payload.paused:
        _remove_ids_from_priority_queue([product_id], source="user_paused")
    else:
        #Reinserção na fila de prioridade (substituiu o enqueue que estava no CRUD)
        _enqueue_monitored_at_priority_queue(monitored, reference=reference, source="user_resumed")
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
    """ Remove monitorado com lock Redis e limpeza da fila de prioridade.

    A sessão é sempre recebida da camada de rota para manter o padrão de
    injeção de dependências (CRUD recebe Session e nunca instancia SessionLocal).
    """
    lock_owner: str | None = None
    try:
        lock_owner = _acquire_monitored_lock(product_id)
        deleted_ids = delete_monitored(db, product_id, user)
    except Exception as exc:
        _raise_from_monitored_error(exc)
        return
    finally:
        if lock_owner:
            release_product_lock(product_id, lock_owner)

    _remove_ids_from_priority_queue(deleted_ids, source="monitored_deleted")
