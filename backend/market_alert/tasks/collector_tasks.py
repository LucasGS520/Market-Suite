""" Tarefa Celery dedicada a coletar um único produto via scraping.

O módulo atua como adaptador fino entre a fila de coleta e os serviços de
scraping, garantindo que cada execução processe apenas um monitorado ou
concorrente. A responsabilidade de orquestração e comparação permanece nas
tasks de monitoramento, reduzindo duplicidade e facilitando observabilidade.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Mapping
from uuid import UUID

import structlog
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
    COLLECTOR_NO_DATA_TOTAL,
    COLLECTOR_SUCCESS_NEW_DATA_TOTAL,
    COLLECTOR_SUCCESS_NO_CHANGE_TOTAL,
    SCRAPER_IN_FLIGHT,
)
from shared.utils.redis_client import is_scraping_suspended
from shared.utils.redis_locks import acquire_product_lock, release_product_lock

from market_alert.core.celery_app import celery_app
from market_alert.services.services_scraper_competitor import scrape_competitor_product
from market_alert.services.services_scraper_monitored import scrape_monitored_product
from market_alert.tasks.compare_prices_tasks import compare_prices_task


logger = structlog.get_logger("collector_tasks")

def _validate_payload(payload: Mapping[str, str] | None) -> tuple[str, UUID | None, UUID | None, str | None]:
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
) -> str:
    """ Atualiza métricas por desfecho e retorna rótulo normalizado.

    O parâmetro ``lock_status`` admite ``acquired`` (lock aplicado),
    ``skipped`` (não adquirido) ou ``not_used`` (monitoramento com flag
    ``checking_in_progress``). Dessa forma mantemos contadores
    consistentes sem forçar métricas de lock quando o controle de
    concorrência for feito apenas via banco de dados. A normalização
    garante que mesmo cenários de lock não adquirido reportem ``no_result``
    para manter o contrato mínimo esperado pelo orquestrador. O campo
    ``reason`` preserva o motivo interno para logs, mas sempre retorna um
    status contratual.
    """
    if lock_status == "skipped":
        COLLECTOR_LOCK_SKIPPED_TOTAL.labels(kind=kind).inc()
        COLLECTOR_NO_DATA_TOTAL.labels(kind=kind).inc()
        return "no_result"
    
    if reason == "scraping_suspended":
        COLLECTOR_NO_DATA_TOTAL.labels(kind=kind).inc()
        return "no_result"

    if reason == "invalid_payload":
        COLLECTOR_ERROR_TOTAL.labels(kind=kind).inc()
        return "error"

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
        return "success"

    COLLECTOR_ERROR_TOTAL.labels(kind=kind).inc()
    return "error"

def _dispatch_comparison(monitored_id: UUID | None, result: ScrapeResult | None) -> None:
    """ Agenda comparação apenas quando scraping trouxe alteração relevante """
    if monitored_id is None or result is None:
        return
    
    changed = bool(getattr(result, "price_changed", False) or getattr(result, "availability_changed", False))
    if changed:
        compare_prices_task.apply_async(args=[str(monitored_id)], queue="monitor")


def collect_product(
    payload: Mapping[str, str] | None,
    *,
    use_lock: bool = True,
    dispatch_comparison: bool = True,
    lock_ttl_seconds: int | None = None,
    logger_bound=None,
) -> tuple[str, ScrapeResult | None]:
    """ Executa coleta de produto de forma reutilizável para tasks e orquestradores.

    A função aplica validação de payload, coordena lock distribuído quando
    ``use_lock`` estiver habilitado e registra métricas consistentes. Quando
    utilizada pelo monitorador, ``use_lock`` deve permanecer ``False`` para
    que a exclusão mútua seja controlada apenas pela flag
    ``checking_in_progress``. O TTL do lock segue
    ``PRODUCT_LOCK_TTL_SECONDS`` ou o valor informado em
    ``lock_ttl_seconds``.
    """
    SCRAPER_IN_FLIGHT.inc()
    started_at = datetime.now(timezone.utc)
    task_logger = logger_bound or logger

    kind, monitored_id, competitor_id, url = _validate_payload(payload)
    lock_target = competitor_id or monitored_id

    lock_status = "not_used"
    
    reason: str | None = None
    result: ScrapeResult | None = None
    lock_acquired = False

    try:
        if payload is None or lock_target is None or url is None:
            reason = "invalid_payload"
            task_logger.error("invalid_payload", kind=kind)
        elif is_scraping_suspended():
            reason = "scraping_suspended"
            task_logger.warning("scraping_suspended", kind=kind, product_id=str(lock_target))
        else:
            if use_lock:
                lock_acquired = acquire_product_lock(lock_target, ttl_seconds=lock_ttl_seconds)
                lock_status = "acquired" if lock_acquired else "skipped"
                if lock_acquired:
                    COLLECTOR_LOCK_ACQUIRED_TOTAL.labels(kind=kind).inc()
                else:
                    reason = "lock_skipped"
                    task_logger.info(
                        "collect_skipped_lock",
                        kind=kind,
                        product_id=str(lock_target),
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
                    if competitor_id is not None:
                        payload_model = CompetitorProductCreateScraping(
                            monitored_product_id=monitored_id,
                            product_url=url,
                        )
                        result = scrape_competitor_product(
                            db=db,
                            user_id=user_uuid or monitored_id or competitor_id,
                            url=url,
                            payload=payload_model,
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
                        )
    except ScraperError as exc:
        reason = "scraper_error"
        task_logger.warning("scraper_error", kind=kind, error=str(exc))
    except Exception:
        reason = "unexpected_error"
        task_logger.exception("collect_unexpected", kind=kind)
    finally:
        outcome = _record_metrics(kind, result, lock_status=lock_status, reason=reason)
        if use_lock and lock_acquired:
            release_product_lock(lock_target)
        SCRAPER_IN_FLIGHT.dec()
        duration_ms = int((datetime.now(timezone.utc) - started_at).total_seconds() * 1000)
        task_logger.info(
            "collect_product_finished",
            kind=kind,
            duration_ms=duration_ms,
            outcome=outcome,
            reason=reason,
            lock_status=lock_status,
            monitored_id=str(monitored_id) if monitored_id else None,
            competitor_id=str(competitor_id) if competitor_id else None,
        )
        if dispatch_comparison:
            _dispatch_comparison(monitored_id, result)

    return outcome, result

@celery_app.task(
    bind=True,
    max_retries=0,
    name="market_alert.tasks.collector_tasks.collect_product_task",
    queue="scraping",
    acks_late=True,
)
def collect_product_task(self, payload: Mapping[str, str] | None = None) -> str:
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
