""" Tarefa Celery dedicada a coletar um único produto via scraping.

O módulo atua como adaptador fino entre a fila de coleta e os serviços de
scraping, garantindo que cada execução processe apenas um monitorado ou
concorrente. Rechecagens e coletas manuais compartilham este mesmo fluxo e
apenas o lock Redis aplicado aqui é utilizado para exclusão mútua.
"""
from __future__ import annotations

import time
from datetime import datetime, timezone
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
from shared.utils.trace_context import set_trace_id
from shared.utils.redis_client import is_scraping_suspended
from shared.utils.redis_locks import acquire_product_lock, release_product_lock

from market_alert.core.celery_app import celery_app
from market_alert.core.config_alert import settings
from market_alert.core.dlq_base_task import DLQTask
from market_alert.core.retry_policies import COLLECTION_RETRY
from market_alert.crud.crud_monitored import (
    activate_pending_monitored,
    get_monitored_product_by_id,
    mark_monitored_product_failed,
)
from market_alert.crud.crud_competitor import (
    get_competitor_by_id,
    update_competitor_pause_state,
)
from market_alert.services.services_scraper_competitor import scrape_competitor_product
from market_alert.services.services_scraper_monitored import scrape_monitored_product
from market_alert.scraper.scraper_client import ScraperClientError
from market_alert.infra.celery.retry_policies import RetryPolicy
from market_alert.schemas.schemas_collection_payload import validate_payload as validate_collection_payload
from market_alert.utils.price_comparator import _parse_force_compare_, schedule_comparison_after_commit
from market_alert.utils.collector_result import (
    INVALID_URL_ERRORS_CODES,
    _extract_host,
    _is_rate_limit_error,
    _resolve_no_result_reason,
    _resolve_outcome,
    _should_block_invalid_url,
    _should_schedule_temporary_retry,
    _validate_payload,
)
from market_alert.utils.rate_limiter import (
    _increment_invalid_url_attempt,
    _increment_temporary_failure_attempt,
    _register_scrape_cooldown,
    _reset_invalid_url_attempt,
    _reset_temporary_failure_attempt,
)


logger = structlog.get_logger("collector_product_task")


def collect_product(
    payload: Mapping[str, str | None] | None,
    *,
    use_lock: bool = True,
    dispatch_comparison: bool = True,
    lock_ttl_seconds: int | None = None,
    logger_bound=None,
    db: Session,
) -> tuple[str, ScrapeResult | None, str | None]:
    """ Executa coleta unitária com lock, delegação por tipo e desfecho consolidado. """
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
                lock_acquired, lock_owner = acquire_product_lock(lock_target, ttl_seconds=lock_ttl_seconds)
                lock_status = "acquired" if lock_acquired else "skipped"
                if not lock_acquired:
                    reason = "lock_skipped"
                    result = ScrapeResult(
                        status="no_result",
                        product_id=str(lock_target),
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
                try:
                    raw_user = payload.get("user_id") if payload else None
                    user_uuid = UUID(str(raw_user)) if raw_user else None
                except Exception:
                    user_uuid = None

                def _collect_with_db(session: Session, *, commit_activation: bool) -> tuple[UUID | None, ScrapeResult | None, str | None]:
                    """ Verifica pré-condições via CRUD e delega scraping ao service correto. """
                    if competitor_id is not None:
                        competitor = get_competitor_by_id(session, competitor_id)
                        if competitor is None:
                            task_logger.info(
                                "collect_skipped_missing_competitor",
                                competitor_id=str(competitor_id),
                                monitored_id=str(monitored_id) if monitored_id else None,
                                trace_id=trace_id,
                            )
                            return monitored_id, ScrapeResult(
                                status="no_result",
                                product_id=str(competitor_id),
                                http_status=404,
                                error_code="missing_target",
                            ), "missing_target"

                        resolved_monitored = monitored_id or competitor.monitored_product_id
                        monitored_paused = bool(competitor.monitored_product and competitor.monitored_product.paused)
                        if competitor.is_paused or monitored_paused:
                            task_logger.info(
                                "collector_skipped_paused",
                                competitor_id=str(competitor_id),
                                monitored_id=str(resolved_monitored) if resolved_monitored else None,
                                trace_id=trace_id,
                            )
                            return resolved_monitored, ScrapeResult(
                                status="no_result",
                                product_id=str(competitor_id),
                                http_status=200,
                                error_code="paused",
                            ), "paused"

                        payload_model = CompetitorProductCreateScraping(
                            monitored_product_id=resolved_monitored,
                            product_url=url,
                            name=payload.get("name") if payload else None,
                        )
                        result = scrape_competitor_product(
                            db=session,
                            user_id=user_uuid or resolved_monitored or competitor_id,
                            url=url,
                            payload=payload_model,
                            collected_at=collected_at,
                        )
                        return resolved_monitored, result, None

                    # Branch de monitorado
                    monitored = get_monitored_product_by_id(session, monitored_id) if monitored_id else None
                    if monitored is not None and monitored.paused:
                        task_logger.info(
                            "collect_skipped_paused",
                            monitored_id=str(monitored_id),
                            trace_id=trace_id,
                        )
                        return monitored_id, ScrapeResult(
                            status="no_result",
                            product_id=str(monitored_id) if monitored_id else None,
                            http_status=200,
                            error_code="paused",
                        ), "paused"

                    payload_model = MonitoredProductCreateScraping(
                        name_identification=payload.get("name") if payload else None,
                        product_url=url,
                    )
                    result = scrape_monitored_product(
                        db=session,
                        url=url,
                        user_id=user_uuid or monitored_id,
                        payload=payload_model,
                        collected_at=collected_at,
                    )
                    if result and result.status in {"success", "not_modified"}:
                        activated = activate_pending_monitored(session, monitored_id, commit=commit_activation)
                        if activated is not None:
                            task_logger.info(
                                "monitored_status_activated",
                                monitored_id=str(monitored_id),
                                trace_id=trace_id,
                            )
                    return monitored_id, result, None
                
                monitored_id, result, reason = _collect_with_db(db, commit_activation=False)
                if dispatch_comparison:
                    schedule_comparison_after_commit(
                        db,
                        monitored_id,
                        result,
                        trace_id,
                        force=force_compare,
                    )

    except ScraperClientError as exc:
        reason = "scraper_client_error"
        error_code = "rate_limit" if exc.status_code == 429 else "service_unavailable" if exc.status_code in {503, 504} else "scraper_client_error"
        result = ScrapeResult(
            status="error",
            product_id=str(lock_target) if lock_target else None,
            http_status=exc.status_code,
            error_code=error_code,
            retry_after=exc.retry_after,
        )
        task_logger.warning("scraper_client_error", kind=kind, error=str(exc), http_status=exc.status_code)          
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
        if result is not None and reason is None and (result.error_code or "").strip().lower() in INVALID_URL_ERRORS_CODES:
            reason = "invalid_url"
        if result is not None and result.status == "no_result" and reason is None:
            reason = _resolve_no_result_reason(result)
        
        outcome = _resolve_outcome(kind, result, lock_status=lock_status, reason=reason)
        if use_lock and lock_status == "acquired":
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
    base=DLQTask,
    name="market_alert.tasks.collector_product_task.collect_product_task",
    queue="scraping",
    **COLLECTION_RETRY,
)
def collect_product_task(self, payload: Mapping[str, str | None] | None = None) -> dict[str, Any]:
    """ Coleta um monitorado ou concorrente aplicando lock e retornando desfecho.

    A task valida o payload contra o schema ``CollectionPayload`` antes de
    qualquer lógica. Payloads inválidos retornam ``error`` imediatamente sem
    acionar retry. Em seguida aplica o lock Redis, invoca o serviço de scraping
    e retorna o desfecho para o pipeline. Quando o lock não pode ser adquirido,
    retorna ``no_result`` e agenda retry com backoff leve.
    """
    #Valida o payload contra o schema tipado antes de qualquer outra operação.
    #Payloads antigos (sem version) são aceitos com version=1 como fallback.
    if payload is not None:
        try:
            validated_payload = validate_collection_payload(payload)
            #Reutiliza o payload já validado para propagar trace_id gerado automaticamente e manter rastreabilidade consistente nos logs.
            payload = validated_payload.model_dump(mode="json")
        except ValueError as exc:
            logger.warning(
                "collect_product_task_invalid_payload",
                error=str(exc),
                task_id=getattr(self.request, "id", None),
            )
            return {"outcome": "error", "status": "error", "reason": "invalid_payload", "next_retry_at": None, "product_id": None}

    _trace_id = (payload.get("trace_id") if payload else None) or getattr(self.request, "id", None) or ""
    set_trace_id(_trace_id)

    with SessionLocal() as db:
        # A task mantém sessão única do início ao fim para garantir rastreabilidade e fechamento previsível com contexto.
        outcome, result, reason = collect_product(
            payload,
            use_lock=True,
            dispatch_comparison=True,
            logger_bound=logger.bind(task_id=getattr(self.request, "id", None)),
            db=db,
        )
        if payload is not None:
            kind, monitored_id, competitor_id, _ = _validate_payload(payload)
            lock_target = competitor_id or monitored_id
            trace_id = payload.get("trace_id")
        else:
            kind = "unknown"
            monitored_id = None
            competitor_id = None
            lock_target = None
            trace_id = None

        if payload and lock_target and outcome == "no_result":
            error_code = getattr(result, "error_code", None)
            if error_code == "lock_skipped":
                attempt = int(getattr(self.request, "retries", 0)) + 1
                delay = RetryPolicy.compute_lock_retry_delay(attempt)
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
                        max_retries=RetryPolicy.LOCK_RETRY_MAX_RETRIES,
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
                _blocked_url = payload.get("url") if payload else None
                if monitored_id is not None:
                    mark_monitored_product_failed(db, monitored_id)
                    logger.warning(
                        "scrape_invalid_url_blocked",
                        kind=kind,
                        monitored_id=str(monitored_id),
                        url=_blocked_url,
                        attempts=invalid_attempt,
                        trace_id=trace_id,
                    )
                elif competitor_id is not None:
                    update_competitor_pause_state(db, competitor_id, is_paused=True)
                    logger.warning(
                        "scrape_invalid_url_blocked",
                        kind=kind,
                        competitor_id=str(competitor_id),
                        url=_blocked_url,
                        attempts=invalid_attempt,
                        trace_id=trace_id,
                    )
            else:
                #A policy centraliza cálculo de delay e next_retry_at para manter consistência entre logs, payload de retorno e futuras mudanças.
                base_now = datetime.now(timezone.utc)
                should_retry, next_retry_at = RetryPolicy.should_retry_scrape_failure(
                    "invalid_url",
                    invalid_attempt,
                    max_attempts=settings.SCRAPER_INVALID_URL_MAX_ATTEMPTS,
                    max_seconds=min(RetryPolicy.SCRAPE_RETRY_WINDOW_SECONDS, settings.SCRAPER_MAX_RETRY_DELAY_SECONDS),
                    now=base_now,
                )
                if should_retry and next_retry_at is not None:
                    delay = (next_retry_at - base_now).total_seconds()
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
                ttl_seconds=RetryPolicy.SCRAPE_RETRY_TTL_SECONDS,
            )
            if retry_attempt is None:
                retry_attempt = 1
            if retry_attempt > RetryPolicy.SCRAPE_RETRY_MAX_ATTEMPTS:
                #Reinicia contador para evitar loops infinitos após atingir o limite
                _reset_temporary_failure_attempt(str(lock_target))
                delay = max(30, settings.SCRAPER_NO_RESULT_RETRY_SECONDS)
                base_now = datetime.now(timezone.utc)
                should_retry, next_retry_at = RetryPolicy.should_retry_scrape_failure(
                    reason or "unknown",
                    retry_attempt,
                    max_attempts=retry_attempt,
                    max_seconds=delay,
                    now=base_now,
                )
                if not should_retry:
                    next_retry_at = None
                temporary_failure = True
                logger.warning(
                    "scrape_retry_exhausted",
                    kind=kind,
                    product_id=str(lock_target),
                    trace_id=trace_id,
                    attempts=retry_attempt,
                    delay_seconds=delay,
                    next_retry_at=next_retry_at.isoformat() if next_retry_at else None,
                )
            else:
                #Falhas temporárias padrão usam policy única para evitar divergência de cálculo de next_retry_at entre consumidores.
                base_now = datetime.now(timezone.utc)
                should_retry, next_retry_at = RetryPolicy.should_retry_scrape_failure(
                    reason or "unknown",
                    retry_attempt,
                    retry_after=getattr(result, "retry_after", None),
                    max_seconds=min(RetryPolicy.SCRAPE_RETRY_WINDOW_SECONDS, settings.SCRAPER_MAX_RETRY_DELAY_SECONDS),
                    now=base_now,
                )
                if should_retry and next_retry_at is not None:
                    delay = (next_retry_at - base_now).total_seconds()
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
