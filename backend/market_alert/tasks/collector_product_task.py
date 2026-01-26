""" Tarefa Celery dedicada a coletar um único produto via scraping.

O módulo atua como adaptador fino entre a fila de coleta e os serviços de
scraping, garantindo que cada execução processe apenas um monitorado ou
concorrente. Rechecagens e coletas manuais compartilham este mesmo fluxo e
apenas o lock Redis aplicado aqui é utilizado para exclusão mútua.
"""
from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Mapping
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
from shared.metrics.metrics_scraper import (
    COLLECTOR_ERROR_TOTAL,
    COLLECTOR_LOCK_ACQUIRED_TOTAL,
    COLLECTOR_LOCK_SKIPPED_TOTAL,
    COLLECTOR_LOCK_SKIPPED_OWNER_TOTAL,
    COLLECTOR_NO_DATA_TOTAL,
    COLLECTOR_SUCCESS_NEW_DATA_TOTAL,
    COLLECTOR_SUCCESS_NO_CHANGE_TOTAL,
    COLLECTOR_DURATION_MS,
    COLLECTOR_SKIPPED_MISSING_TARGET_TOTAL,
    COLLECT_LOCK_SKIPPED_TOTAL,
    COLLECT_SUCCESS_TOTAL,
    MONITORED_SKIPPED_PAUSED_TOTAL,
    SCRAPER_IN_FLIGHT,
)
from shared.utils.redis_client import is_scraping_suspended
from shared.utils.redis_locks import acquire_product_lock, release_product_lock

from market_alert.core.celery_app import celery_app
from market_alert.services.services_scraper_competitor import scrape_competitor_product
from market_alert.services.services_scraper_monitored import scrape_monitored_product
from market_alert.models.models_products import CompetitorProduct, MonitoredProduct
from market_alert.enums.enums_products import MonitoredStatus


logger = structlog.get_logger("collector_product_task")

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

def _record_metrics(
    kind: str,
    result: ScrapeResult | None,
    *,
    lock_status: str,
    reason: str | None,
    lock_owner: str | None,
) -> str:
    """ Atualiza métricas por desfecho e retorna rótulo normalizado.

    O parâmetro ``lock_status`` admite ``acquired`` (lock aplicado) ou
    ``skipped`` (não adquirido). A normalização garante que mesmo cenários
    sem lock reportem ``no_result`` para manter o contrato esperado pelo
    orquestrador. O campo ``reason`` preserva o motivo interno para logs,
    mas sempre retorna um status contratual.
    """
    if lock_status == "skipped":
        COLLECTOR_LOCK_SKIPPED_TOTAL.labels(kind=kind).inc()
        COLLECT_LOCK_SKIPPED_TOTAL.labels(kind=kind).inc()
        COLLECTOR_LOCK_SKIPPED_OWNER_TOTAL.labels(kind=kind, owner=lock_owner or "unknown").inc()
        COLLECTOR_NO_DATA_TOTAL.labels(kind=kind).inc()
        return "no_result"
    
    if reason == "scraping_suspended":
        COLLECTOR_NO_DATA_TOTAL.labels(kind=kind).inc()
        return "no_result"

    if reason == "invalid_payload":
        COLLECTOR_ERROR_TOTAL.labels(kind=kind).inc()
        return "error"
    
    if reason == "missing_target":
        COLLECTOR_SKIPPED_MISSING_TARGET_TOTAL.labels(kind=kind).inc()
        COLLECTOR_NO_DATA_TOTAL.labels(kind=kind).inc()
        return "no_result"

    if reason in {"scraper_error", "unexpected_error"}:
        COLLECTOR_ERROR_TOTAL.labels(kind=kind).inc()
        return "error"

    if result is None:
        COLLECTOR_ERROR_TOTAL.labels(kind=kind).inc()
        return "error"
    
    if result.status == "no_result":
        COLLECTOR_NO_DATA_TOTAL.labels(kind=kind).inc()
        return "no_result"

    if result.status == "not_modified":
        COLLECTOR_SUCCESS_NO_CHANGE_TOTAL.labels(kind=kind).inc()
        return "not_modified"

    if result.status == "success":
        COLLECTOR_SUCCESS_NEW_DATA_TOTAL.labels(kind=kind).inc()
        COLLECT_SUCCESS_TOTAL.labels(kind=kind).inc()
        return "success"

    COLLECTOR_ERROR_TOTAL.labels(kind=kind).inc()
    return "error"

def _dispatch_comparison(
    monitored_id: UUID | None,
    result: ScrapeResult | None,
    trace_id: str | None,
    *,
    force: bool = False,
) -> None:
    """ Agenda comparação apenas quando scraping trouxe alteração relevante """
    if monitored_id is None or result is None:
        return
    
    changed = bool(getattr(result, "price_changed", False) or getattr(result, "availability_changed", False))
    if not (force or changed):
        return
    
    #Usa send_task para evitar importação direta e quebrar ciclos entre tasks
    celery_app.send_task(
        "market_alert.tasks.compare_prices_task.compare_prices_task",
        args=[
            str(monitored_id),
            bool(getattr(result, "price_changed", False)),
            bool(getattr(result, "availability_changed", False)),
            trace_id,
        ],
        #Mantém comparação na fila de monitoramento para ser processada pelo worker dedicado
        queue="monitor",
    )
    logger.info(
        "compare_prices_enqueued",
        monitored_id=str(monitored_id),
        trace_id=trace_id,
        forced=force,
        changed=changed,
    )

def _parse_force_compare_(value: str | None) -> bool:
    """ Normaliza o flag de disparo forçado para comparação """
    if value is None:
        return False
    return str(value).strip().lower() in {"1", "true", "yes", "on"}

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

def collect_product(
    payload: Mapping[str, str | None] | None,
    *,
    use_lock: bool = True,
    dispatch_comparison: bool = True,
    lock_ttl_seconds: int | None = None,
    logger_bound=None,
) -> tuple[str, ScrapeResult | None]:
    """ Executa coleta de produto de forma reutilizável para tasks e orquestradores.

    A função aplica validação de payload, coordena lock distribuído quando
    ``use_lock`` estiver habilitado e registra métricas consistentes. O TTL
    do lock segue ``PRODUCT_LOCK_TTL_SECONDS`` ou o valor informado em
    ``lock_ttl_seconds``.
    """
    SCRAPER_IN_FLIGHT.inc()
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
                if lock_acquired:
                    COLLECTOR_LOCK_ACQUIRED_TOTAL.labels(kind=kind).inc()
                else:
                    reason = "lock_skipped"
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

                with SessionLocal() as db:
                    competitor_row: CompetitorProduct | None = None
                    if competitor_id is not None:
                        competitor_row = (
                            db.query(CompetitorProduct)
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
                            MONITORED_SKIPPED_PAUSED_TOTAL.labels(source="collector").inc()
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
                                error_code=None,
                            )
                        else:
                            payload_model = CompetitorProductCreateScraping(
                                monitored_product_id=monitored_id,
                                product_url=url,
                            )
                            result = scrape_competitor_product(
                                db=db,
                                user_id=user_uuid or monitored_id or competitor_id,
                                url=url,
                                payload=payload_model,
                                collected_at=collected_at,
                            )
                    else:
                        monitored_row: MonitoredProduct | None = None
                        if monitored_id is not None:
                            monitored_row = (
                                db.query(MonitoredProduct)
                                .filter(MonitoredProduct.id == monitored_id)
                                .first()
                            )

                        if monitored_row is not None and monitored_row.paused:
                            reason = "paused"
                            MONITORED_SKIPPED_PAUSED_TOTAL.labels(source="collector").inc()
                            task_logger.info(
                                "collect_skipped_paused",
                                monitored_id=str(monitored_id),
                                trace_id=trace_id,
                            )
                            result = ScrapeResult(
                                status="no_result",
                                product_id=str(monitored_id) if monitored_id else None,
                                http_status=200,
                                error_code=None,
                            )
                        else:
                            payload_model = MonitoredProductCreateScraping(
                                name_identification=payload.get("name") if payload else None,
                                product_url=url,
                            )
                            result = scrape_monitored_product(
                                db=db,
                                url=url,
                                user_id=user_uuid or monitored_id,
                                payload=payload_model,
                                collected_at=collected_at,
                            )
                            if result and result.status in {"success", "not_modified"}:
                                #Garante a transição para ativo mesmo que o fluxo anterior não tenha persistido
                                _activate_pending_monitored(
                                    db,
                                    monitored_id,
                                    task_logger=task_logger,
                                    trace_id=trace_id,
                                )
    except ScraperError as exc:
        reason = "scraper_error"
        task_logger.warning("scraper_error", kind=kind, error=str(exc))
    except Exception:
        reason = "unexpected_error"
        task_logger.exception("collect_unexpected", kind=kind)
    finally:
        duration_ms = int((time.perf_counter() - started_perf) * 1000)
        outcome = _record_metrics(
            kind,
            result,
            lock_status=lock_status,
            reason=reason,
            lock_owner=lock_owner,
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
        SCRAPER_IN_FLIGHT.dec()
        COLLECTOR_DURATION_MS.labels(kind=kind, outcome=outcome).observe(duration_ms)
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
        if dispatch_comparison:
            _dispatch_comparison(monitored_id, result, trace_id, force=force_compare)

    return outcome, result

@celery_app.task(
    bind=True,
    max_retries=0,
    name="market_alert.tasks.collector_product_task.collect_product_task",
    queue="scraping",
    acks_late=True,
    soft_time_limit=90,
    time_limit=120,
)
def collect_product_task(self, payload: Mapping[str, str | None] | None = None) -> str:
    """Coleta um monitorado ou concorrente aplicando lock e retornando desfecho.

    A task valida o payload mínimo, aplica o lock Redis para o produto alvo e
    invoca o serviço de scraping adequado. Não executa orquestrações extras,
    mantendo a granularidade por item e favorecendo retries simples. Quando o
    lock não pode ser adquirido, retorna ``no_result`` para manter o contrato
    de status enxuto previsto pelo pipeline.
    """
    outcome, _ = collect_product(
        payload,
        use_lock=True,
        dispatch_comparison=True,
        logger_bound=logger.bind(task_id=getattr(self.request, "id", None)),
    )
    return outcome
