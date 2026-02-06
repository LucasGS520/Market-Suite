""" Tarefa Celery dedicada a coletar um único produto via scraping.

O módulo atua como adaptador fino entre a fila de coleta e os serviços de
scraping, garantindo que cada execução processe apenas um monitorado ou
concorrente. Rechecagens e coletas manuais compartilham este mesmo fluxo e
apenas o lock Redis aplicado aqui é utilizado para exclusão mútua.
"""
from __future__ import annotations

import time
import random
from datetime import datetime, timedelta, timezone
from typing import Any, Mapping
from uuid import UUID

import structlog
from sqlalchemy.orm import Session
from backend.shared.schemas.shared_schemas_products import (
    CompetitorProductCreateScraping,
    MonitoredProductCreateScraping,
)
from backend.shared.schemas.shared_schemas_scraper import ScrapeResult

from shared.exceptions import ScraperError
from shared.infra.db import SessionLocal
from shared.utils.redis_client import is_scraping_suspended
from shared.utils.redis_locks import acquire_product_lock, release_product_lock

from market_alert.core.celery_app import celery_app
from market_alert.core.config_alert import settings
from market_alert.services.services_scraper_competitor import scrape_competitor_product
from market_alert.services.services_scraper_monitored import scrape_monitored_product
from market_alert.models.models_products import CompetitorProduct, MonitoredProduct
from market_alert.enums.enums_products import MonitoredStatus
from market_alert.scraper.scraper_client import ScraperClientError
from market_alert.utils.price_comparator import _parse_force_compare_, _schedule_comparison_after_commit
from market_alert.utils.collector_result import (
    INVALID_URL_ERRORS_CODES,
    _extract_host,
    _is_rate_limit_error,
    _resolve_no_result_reason,
    _resolve_outcome,
    _should_block_invalid_url,
    _should_schedule_temporary_retry,
)
from market_alert.utils.rate_limiter import (
    _increment_invalid_url_attempt,
    _increment_temporary_failure_attempt,
    _register_scrape_cooldown,
    _reset_invalid_url_attempt,
    _reset_temporary_failure_attempt,
)


logger = structlog.get_logger("collector_product_task")

LOCK_RETRY_BASE_SECONDS = 5
LOCK_RETRY_MAX_SECONDS = 60
LOCK_RETRY_MAX_RETRIES = 3
LOCK_RETRY_JITTER_RATIO = 0.2
SCRAPE_RETRY_BASE_SECONDS = 30
SCRAPE_RETRY_MAX_SECONDS = 15 * 60
SCRAPE_RETRY_MAX_ATTEMPTS = 5
SCRAPE_RETRY_JITTER_RATIO = 0.3
SCRAPE_RETRY_TTL_SECONDS = 60 * 60

def _compute_lock_retry_delay(
    attempt: int,
    *,
    base_seconds: int = LOCK_RETRY_BASE_SECONDS,
    max_seconds: int = LOCK_RETRY_MAX_SECONDS,
    jitter_ratio: float = LOCK_RETRY_JITTER_RATIO,
) -> int:
    """ Calcula atraso para retry com backoff exponencial e jitter leve """
    sanitized_attempt = max(1, attempt)
    exponential_delay = base_seconds * (2 ** (sanitized_attempt - 1))
    capped_delay = min(exponential_delay, max_seconds)
    #Aplica jitter leve para evitar colisão de reexecuções simultâneas
    jitter_multiplier = 1 + ((random.random() * 2) - 1) * jitter_ratio
    delay = int(max(1, capped_delay * jitter_multiplier))
    return delay

def _compute_scrape_retry_delay(
    attempt: int,
    *,
    base_seconds: int = SCRAPE_RETRY_BASE_SECONDS,
    max_seconds: int = SCRAPE_RETRY_MAX_SECONDS,
    jitter_ratio: float = SCRAPE_RETRY_JITTER_RATIO,
    retry_after: int | None = None,
) -> int:
    """ Calcula atraso para falhas temporárias usando backoff e ``Retry-After`` """
    if retry_after is not None and retry_after > 0:
        return int(min(retry_after, max_seconds))
    return _compute_lock_retry_delay(
        attempt,
        base_seconds=base_seconds,
        max_seconds=max_seconds,
        jitter_ratio=jitter_ratio,
    )

def _validate_payload(payload: Mapping[str, str | None] | None) -> tuple[str, UUID | None, UUID | None, str | None]:
    """ Valida campos mínimos, retornando tipo, IDs e URL.

    A validação impede que a tarefa tente acessar campos ausentes e garante
    que tenhamos um identificador claro para aplicar o lock. Em caso de
    inconsistências retornamos identificadores nulos para facilitar logs.
    """
    if payload is None:
        return "unknown", None, None, None

    competitor_id_value = payload.get("competitor_id")
    monitored_id_value = payload.get("monitored_id")
    url = payload.get("url")

    competitor_id = None
    monitored_id = None

    try:
        competitor_id = UUID(str(competitor_id_value)) if competitor_id_value else None
    except Exception:
        competitor_id = None

    try:
        monitored_id = UUID(str(monitored_id_value)) if monitored_id_value else None
    except Exception:
        monitored_id = None

    kind = "competitor" if competitor_id is not None else "monitored"
    if monitored_id is None and competitor_id is None:
        kind = payload.get("kind", "unknown") or "unknown"

    return kind, monitored_id, competitor_id, url

def _activate_pending_monitored(
    db: Session,
    monitored_id: UUID | None,
    *,
    task_logger,
    trace_id: str | None,
) -> None:
    """ Atualiza monitorado pendente para ativo após coleta bem-sucedida """
    if monitored_id is None:
        return
    
    monitored = (
        db.query(MonitoredProduct)
        .filter(MonitoredProduct.id == monitored_id)
        .first()
    )
    if monitored is None:
        return
    
    if monitored.status != MonitoredStatus.pending:
        return
    
    monitored.status = MonitoredStatus.active
    db.commit()
    db.refresh(monitored)
    task_logger.info(
        "monitored_status_activated",
        monitored_id=str(monitored_id),
        trace_id=trace_id,
    )

def _mark_invalid_product(
    *,
    monitored_id: UUID | None,
    competitor_id: UUID | None,
    kind: str,
    url: str | None,
    attempts: int,
    trace_id: str | None,
) -> None:
    """ Marca produto como inválido após falhas repetidas de URL """
    if monitored_id is None and competitor_id is None:
        return
    with SessionLocal() as db:
        if monitored_id is not None:
            from market_alert.crud.crud_monitored import mark_monitored_product_failed
            mark_monitored_product_failed(db, monitored_id)
            logger.warning(
                "scrape_invalid_url_blocked",
                kind=kind,
                monitored_id=str(monitored_id),
                url=url,
                attempts=attempts,
                trace_id=trace_id,
            )
            return
        if competitor_id is not None:
            from market_alert.crud.crud_competitor import update_competitor_pause_state
            update_competitor_pause_state(db, competitor_id, is_paused=True)
            logger.warning(
                "scrape_invalid_url_blocked",
                kind=kind,
                competitor_id=str(competitor_id),
                url=url,
                attempts=attempts,
                trace_id=trace_id,
            )

def collect_product(
    payload: Mapping[str, str | None] | None,
    *,
    use_lock: bool = True,
    dispatch_comparison: bool = True,
    lock_ttl_seconds: int | None = None,
    logger_bound=None,
    db: Session | None = None,
) -> tuple[str, ScrapeResult | None, str | None]:
    """ Executa coleta de produto de forma reutilizável para tasks e orquestradores.

    A função aplica validação de payload e coordena lock distribuído quando
    ``use_lock`` estiver habilitado. O TTL do lock segue ``PRODUCT_LOCK_TTL_SECONDS``
    ou valor informado em  ``lock_ttl_seconds``. Quando ``db`` é fornecida, 
    reutilizamos a sessão compartilhada para garantir consistência transacional e reduzir 
    overhead de conexões, mantendo commits e refresh no mesmo contexto.
    """
    #Mede latência com relógio monotônico para evitar valores negativos
    started_perf = time.perf_counter()
    task_logger = logger_bound or logger

    kind, monitored_id, competitor_id, url = _validate_payload(payload)
    trace_id = payload.get("trace_id") if payload else None
    enqueued_at = payload.get("enqueued_at") if payload else None
    lock_target = competitor_id or monitored_id
    force_compare = _parse_force_compare_(payload.get("force_compare") if payload else None)

    lock_status = "not_used"
    
    reason: str | None = None
    result: ScrapeResult | None = None
    lock_owner: str | None = None

    try:
        collected_at = datetime.now(timezone.utc)
        if payload is None or lock_target is None or url is None:
            reason = "invalid_payload"
            task_logger.error("invalid_payload", kind=kind)
        elif is_scraping_suspended():
            reason = "scraping_suspended"
            task_logger.warning("scraping_suspended", kind=kind, product_id=str(lock_target))
        else:
            if use_lock:
                lock_acquired, resolved_owner = acquire_product_lock(lock_target, ttl_seconds=lock_ttl_seconds)
                lock_owner = resolved_owner
                lock_status = "acquired" if lock_acquired else "skipped"
                if not lock_acquired:
                    reason = "lock_skipped"
                    #Garante retorno explícito para rastrear locks no worker contínuo
                    result = ScrapeResult(
                        status="no_result",
                        product_id=str(lock_target) if lock_target else None,
                        http_status=200,
                        error_code="lock_skipped",
                    )
                    task_logger.info(
                        "collect_skipped_lock",
                        kind=kind,
                        product_id=str(lock_target),
                        trace_id=trace_id,
                        lock_owner=lock_owner,
                        note="retornando no_result para manter contrato minimalista",
                    )

            if reason is None:
                user_uuid = None
                try:
                    raw_user = payload.get("user_id") if payload else None
                    user_uuid = UUID(str(raw_user)) if raw_user else None
                except Exception:
                    user_uuid = None

                def _collect_with_db(session_manager: Session) -> None:
                    nonlocal monitored_id, reason, result

                    competitor_row: CompetitorProduct | None = None
                    if competitor_id is not None:
                        competitor_row = (
                            session_manager.query(CompetitorProduct)
                            .filter(CompetitorProduct.id == competitor_id)
                            .first()
                        )

                    if competitor_id is not None and competitor_row is None:
                        reason = "missing_target"
                        task_logger.info(
                            "collect_skipped_missing_competitor",
                            competitor_id=str(competitor_id),
                            monitored_id=str(monitored_id) if monitored_id else None,
                            trace_id=trace_id,
                        )
                        result = ScrapeResult(
                            status="no_result",
                            product_id=str(competitor_id),
                            http_status=404,
                            error_code="missing_target",
                        )
                    elif competitor_id is not None:
                        monitored_id = monitored_id or competitor_row.monitored_product_id if competitor_row else monitored_id
                        monitored_paused = bool(
                            competitor_row.monitored_product and competitor_row.monitored_product.paused
                        )
                        if competitor_row.is_paused or monitored_paused:
                            reason = "paused"
                            #Evita scraping quando o concorrente ou o monitorado está pausado
                            task_logger.info(
                                "collector_skipped_paused",
                                competitor_id=str(competitor_id),
                                monitored_id=str(monitored_id) if monitored_id else None,
                                trace_id=trace_id,
                            )
                            result = ScrapeResult(
                                status="no_result",
                                product_id=str(competitor_id),
                                http_status=200,
                                error_code="paused",
                            )
                        else:
                            payload_model = CompetitorProductCreateScraping(
                                monitored_product_id=monitored_id,
                                product_url=url,
                                #Preserva o nome personalizado quando vier no payload original
                                name=payload.get("name") if payload else None,
                            )
                            result = scrape_competitor_product(
                                db=session_manager,
                                user_id=user_uuid or monitored_id or competitor_id,
                                url=url,
                                payload=payload_model,
                                collected_at=collected_at,
                            )
                    else:
                        monitored_row: MonitoredProduct | None = None
                        if monitored_id is not None:
                            monitored_row = (
                                session_manager.query(MonitoredProduct)
                                .filter(MonitoredProduct.id == monitored_id)
                                .first()
                            )

                        if monitored_row is not None and monitored_row.paused:
                            reason = "paused"
                            task_logger.info(
                                "collect_skipped_paused",
                                monitored_id=str(monitored_id),
                                trace_id=trace_id,
                            )
                            result = ScrapeResult(
                                status="no_result",
                                product_id=str(monitored_id) if monitored_id else None,
                                http_status=200,
                                error_code="paused",
                            )
                        else:
                            payload_model = MonitoredProductCreateScraping(
                                name_identification=payload.get("name") if payload else None,
                                product_url=url,
                            )
                            result = scrape_monitored_product(
                                db=session_manager,
                                url=url,
                                user_id=user_uuid or monitored_id,
                                payload=payload_model,
                                collected_at=collected_at,
                            )
                            if result and result.status in {"success", "not_modified"}:
                                #Garante a transição para ativo mesmo que o fluxo anterior não tenha persistido
                                _activate_pending_monitored(
                                    session_manager,
                                    monitored_id,
                                    task_logger=task_logger,
                                    trace_id=trace_id,
                                )

                #Mantém a sessão compartilhada quando fornecida para preservar consistência transacional.
                if db is None:
                    with SessionLocal() as session_manager:
                        _collect_with_db(session_manager)
                        if dispatch_comparison:
                            _schedule_comparison_after_commit(
                                session_manager,
                                monitored_id,
                                result,
                                trace_id,
                                force=force_compare,
                            )
                else:
                    _collect_with_db(db)
                    if dispatch_comparison:
                        _schedule_comparison_after_commit(
                            db,
                            monitored_id,
                            result,
                            trace_id,
                            force=force_compare,
                        )

    except ScraperClientError as exc:
        reason = "scraper_client_error"
        error_code = "scraper_client_error"
        if exc.status_code == 429:
            error_code = "rate_limit"
        elif exc.status_code in {503, 504}:
            error_code = "service_unavailable"
        result = ScrapeResult(
            status="error",
            product_id=str(lock_target) if lock_target else None,
            http_status=exc.status_code,
            error_code=error_code,
            retry_after=exc.retry_after,
        )
        task_logger.warning(
            "scraper_client_error",
            kind=kind,
            error=str(exc),
            http_status=exc.status_code,
        )
                            
    except ScraperError as exc:
        reason = "scraper_error"
        result = ScrapeResult(
            status="error",
            product_id=str(lock_target) if lock_target else None,
            http_status=exc.status_code,
            error_code="scraper_error",
        )
        task_logger.warning("scraper_error", kind=kind, error=str(exc))
    except Exception:
        reason = "unexpected_error"
        result = ScrapeResult(
            status="error",
            product_id=str(lock_target) if lock_target else None,
            error_code="unexpected_error",
        )
        task_logger.exception("collect_unexpected", kind=kind)
    finally:
        duration_ms = int((time.perf_counter() - started_perf) * 1000)
        if result is not None and reason is None:
            error_code = (result.error_code or "").strip().lower()
            if error_code in INVALID_URL_ERRORS_CODES:
                reason = "invalid_url"
        if result is not None and result.status == "no_result" and reason is None:
            #Garante que ``no_result`` sempre carregue motivo descritivo para diagnóstico
            reason = _resolve_no_result_reason(result)
        outcome = _resolve_outcome(
            kind,
            result,
            lock_status=lock_status,
            reason=reason,
        )
        if use_lock and lock_status == "acquired":
            #Tentativa explícita de liberar o lock para evitar contenção após falhas
            released = release_product_lock(lock_target, lock_owner)
            if not released:
                task_logger.warning(
                    "collect_lock_release_failed",
                    product_id=str(lock_target) if lock_target else None,
                    trace_id=trace_id,
                )
        task_logger.info(
            "collect_product_finished",
            kind=kind,
            duration_ms=duration_ms,
            outcome=outcome,
            reason=reason,
            lock_status=lock_status,
            monitored_id=str(monitored_id) if monitored_id else None,
            competitor_id=str(competitor_id) if competitor_id else None,
            trace_id=trace_id,
            enqueued_at=enqueued_at,
        )

    return outcome, result, reason

@celery_app.task(
    bind=True,
    max_retries=LOCK_RETRY_MAX_RETRIES,
    name="market_alert.tasks.collector_product_task.collect_product_task",
    queue="scraping",
    acks_late=True,
    soft_time_limit=90,
    time_limit=120,
)
def collect_product_task(self, payload: Mapping[str, str | None] | None = None) -> dict[str, Any]:
    """Coleta um monitorado ou concorrente aplicando lock e retornando desfecho.

    A task valida o payload mínimo, aplica o lock Redis para o produto alvo e
    invoca o serviço de scraping adequado. Não executa orquestrações extras,
    mantendo a granularidade por item e favorecendo retries simples. Quando o
    lock não pode ser adquirido, retorna ``no_result`` para manter o contrato
    de status enxuto previsto pelo pipeline e agenda retry com backoff leve.
    """
    outcome, result, reason = collect_product(
        payload,
        use_lock=True,
        dispatch_comparison=True,
        logger_bound=logger.bind(task_id=getattr(self.request, "id", None)),
    )
    if payload is not None:
        kind, monitored_id, competitor_id, _ = _validate_payload(payload)
        lock_target = competitor_id or monitored_id
        trace_id = payload.get("trace_id")
    else:
        kind = "unknown"
        lock_target = None
        trace_id = None

    if payload and lock_target and outcome == "no_result":
        error_code = getattr(result, "error_code", None)
        if error_code == "lock_skipped":
            attempt = int(getattr(self.request, "retries", 0)) + 1
            delay = _compute_lock_retry_delay(attempt)
            logger.warning(
                "collect_lock_retry_scheduled",
                kind=kind,
                product_id=str(lock_target),
                trace_id=trace_id,
                attempt=attempt,
                delay_seconds=delay,
            )
            try:
                #Evita disparar exceção para manter o retorno compatível com o contrato
                self.retry(
                    countdown=delay,
                    max_retries=LOCK_RETRY_MAX_RETRIES,
                    throw=False,
                )
            except self.MaxRetriesExceededError:
                logger.warning(
                    "collect_lock_retry_exhausted",
                    kind=kind,
                    product_id=str(lock_target),
                    trace_id=trace_id,
                    attempt=attempt,
                )
    temporary_failure = False
    blocked_invalid = False
    next_retry_at = None
    retry_attempt = None
    if payload and lock_target and _should_block_invalid_url(result):
        invalid_attempt = _increment_invalid_url_attempt(
            str(lock_target),
            ttl_seconds=settings.SCRAPER_INVALID_URL_TTL_SECONDS,
        )
        if invalid_attempt is None:
            invalid_attempt = 1
        if invalid_attempt >= settings.SCRAPER_INVALID_URL_MAX_ATTEMPTS:
            _reset_invalid_url_attempt(str(lock_target))
            blocked_invalid = True
            reason = "invalid_url_blocked"
            _mark_invalid_product(
                monitored_id=monitored_id,
                competitor_id=competitor_id,
                kind=kind,
                url=payload.get("url") if payload else None,
                attempts=invalid_attempt,
                trace_id=trace_id,
            )
        else:
            now = datetime.now(timezone.utc)
            delay = _compute_scrape_retry_delay(
                invalid_attempt,
                max_seconds=min(SCRAPE_RETRY_MAX_SECONDS, settings.SCRAPER_MAX_RETRY_DELAY_SECONDS),
            )
            next_retry_at = now + timedelta(seconds=delay)
            temporary_failure = True
            logger.warning(
                "scrape_invalid_url_retry_scheduled",
                kind=kind,
                product_id=str(lock_target),
                trace_id=trace_id,
                attempts=invalid_attempt,
                delay_seconds=delay,
                next_retry_at=next_retry_at.isoformat(),
            )
    
    if payload and lock_target and _should_schedule_temporary_retry(result, reason) and not blocked_invalid:
        retry_attempt = _increment_temporary_failure_attempt(
            str(lock_target),
            ttl_seconds=SCRAPE_RETRY_TTL_SECONDS,
        )
        if retry_attempt is None:
            retry_attempt = 1
        now = datetime.now(timezone.utc)
        if retry_attempt > SCRAPE_RETRY_MAX_ATTEMPTS:
            #Reinicia contador para evitar loops infinitos após atingir o limite
            _reset_temporary_failure_attempt(str(lock_target))
            delay = max(30, settings.SCRAPER_NO_RESULT_RETRY_SECONDS)
            next_retry_at = now + timedelta(seconds=delay)
            temporary_failure = True
            logger.warning(
                "scrape_retry_exhausted",
                kind=kind,
                product_id=str(lock_target),
                trace_id=trace_id,
                attempts=retry_attempt,
                delay_seconds=delay,
                next_retry_at=next_retry_at.isoformat(),
            )
        else:
            delay = _compute_scrape_retry_delay(
                retry_attempt,
                max_seconds=min(SCRAPE_RETRY_MAX_SECONDS, settings.SCRAPER_MAX_RETRY_DELAY_SECONDS),
                retry_after=getattr(result, "retry_after", None),
            )
            next_retry_at = now + timedelta(seconds=delay)
            temporary_failure = True
            if _is_rate_limit_error(result, reason):
                _register_scrape_cooldown(
                    str(lock_target),
                    ttl_seconds=settings.SCRAPER_RATE_LIMIT_COOLDOWN_SECONDS,
                )
            logger.warning(
                "scrape_temporary_failure_scheduled",
                kind=kind,
                product_id=str(lock_target),
                trace_id=trace_id,
                host=_extract_host(payload.get("url") if payload else None),
                attempts=retry_attempt,
                delay_seconds=delay,
                next_retry_at=next_retry_at.isoformat(),
            )

    status = "blocked" if blocked_invalid else ("temporary_failure" if temporary_failure else outcome)
    return {
        "outcome": outcome,
        "status": status,
        "reason": reason,
        "next_retry_at": next_retry_at.isoformat() if next_retry_at else None,
        "product_id": str(lock_target) if lock_target else None,
    }
