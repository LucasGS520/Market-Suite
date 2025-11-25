""" Tarefas Celery relacionadas ao scraping de produtos.

Este módulo concentra as tasks responsáveis por coletar dados de produtos
monitorados e de concorrentes, delegando a coleta às funções de serviço
``scrape_monitored_product`` e ``scrape_competitor_product``. Essas
funções cuidam da comunicação com o serviço externo enquanto
as tasks mantêm métricas e tratamento de erros.
"""

from uuid import UUID
from datetime import datetime, timezone
from typing import Any, Mapping

import structlog
from sqlalchemy.orm import Session

from shared.infra.db import SessionLocal
from shared.utils.redis_client import get_redis_client, is_scraping_suspended
from shared.exceptions import ScraperError
from shared.metrics.metrics_scraper import SCRAPING_LATENCY_SECONDS, SCRAPER_HEAD_FAILURES_TOTAL, SCRAPER_IN_FLIGHT
from backend.shared.schemas.shared_schemas_products import MonitoredProductCreateScraping, CompetitorProductCreateScraping
from backend.shared.schemas.shared_schemas_scraper import ScrapeResult
from shared.enums.error_codes import ScrapingErrorType
from shared.utils.url_validation import normalize_product_url

from market_alert.scraper.scraper_client import ScraperClientError

from market_alert.core.config_alert import settings
from market_alert.core.celery_app import celery_app
from market_alert.crud import crud_errors
from market_alert.crud.crud_monitored import (
    get_monitored_product_by_id,
    get_monitored_product_by_user_and_url,
    mark_monitored_product_failed,
)
from market_alert.services.services_scraper_monitored import scrape_monitored_product
from market_alert.services.services_scraper_competitor import scrape_competitor_product
from market_alert.tasks.compare_prices_tasks import compare_prices_task


logger = structlog.get_logger("scraper_tasks")
def _redis_client():
    """Recupera cliente Redis sob demanda evitando inicialização no import"""
    return get_redis_client()

#TTL de idempotência para evitar reprocessamento repetido do mesmo produto
IDEMPOTENCY_TTL_SECONDS = getattr(settings, "SCRAPER_IDEMPOTENCY_TTL_SECONDS", 3600)

def _merge_payload(
    payload: Mapping[str, Any] | None,
    legacy_kwargs: Mapping[str, Any],
) -> dict[str, Any]:
    """ Normaliza o payload aceitando contratos novos e legados """
    merged: dict[str, Any] = {}
    merged.update(payload or {})

    #Mapeia aliases herdados para manter compatibilidade com chamadas existentes
    alias_mapping = {
        "url": ["url"],
        "owner_id": ["owner_id", "user_id"],
        "monitored_id": ["monitored_id"],
        "competitor_id": ["competitor_id"],
        "request_id": ["request_id"],
        "name": ["name", "name_identification"],
    }

    for target_key, aliases in alias_mapping.items():
        if merged.get(target_key) is not None:
            continue
        for alias in aliases:
            if legacy_kwargs.get(alias) is not None:
                merged[target_key] = legacy_kwargs.get(alias)
                break

    return merged

def _request_id_key(request_id: str | None) -> str | None:
    """ Constrói chave de idempotência baseada no ``request_id`` informativo """
    if not request_id:
        return None
    return f"scraper:request:{request_id}"

def _acquire_request_guard(request_id: str | None, *, task_logger) -> bool:
    """ Bloqueia reprocessamento quando mesmo ``request_id`` ja foi processado """
    key = _request_id_key(request_id)
    client = _redis_client()
    if key is None or client is None:
        return True
    
    acquired = bool(client.set(key, "1", nx=True, ex=IDEMPOTENCY_TTL_SECONDS))
    if not acquired:
        task_logger.info("request_idempotency_skip", request_id=request_id)
    return acquired

def _normalized_timestamp(value: datetime | None) -> datetime:
    """ Normaliza timestamp para UTC e remove microssegundos para chaves estáveis """
    base = value or datetime.now(timezone.utc)
    if base.tzinfo is None:
        base = base.replace(tzinfo=timezone.utc)
    return base.astimezone(timezone.utc).replace(microsecond=0)

def _build_idempotency_key(
    monitored_id: str | UUID | None,
    *,
    reference: datetime | None,
) -> str | None:
    """ Monta chave de deduplicação baseada no monitorado e referência temporal """
    if monitored_id is None:
        return None
    
    reference_value = _normalized_timestamp(reference) if reference else None
    suffix = reference_value.isoformat() if reference_value else "none"
    return f"scraper:idempotent:{monitored_id}:{suffix}"

def _acquire_idempotency_slot(key: str | None, *, task_logger) -> bool:
    """ Registra execução em Redis evitando execuções duplicadas do mesmo payload """
    client = _redis_client()
    if key is None or client is None:
        return True
    
    acquired = bool(client.set(key, "1", nx=True, ex=IDEMPOTENCY_TTL_SECONDS))
    if not acquired:
        task_logger.info("idempotency_skip", key=key)
    return acquired

def _extract_comparison_reference(
    db: Session | None,
    monitored_id: str | UUID | None,
) -> datetime | None:
    """ Recupera referência temporal usada para montar a chave de idempotência """
    if db is None or monitored_id is None or not hasattr(db, "query"):
        return None

    try:
        monitored_uuid = monitored_id if isinstance(monitored_id, UUID) else UUID(str(monitored_id))
    except (TypeError, ValueError):
        return None

    try:
        monitored = get_monitored_product_by_id(db, monitored_uuid)
    except Exception:
        return None

    if monitored is None:
        return None

    reference = getattr(monitored, "last_checked", None)
    if isinstance(reference, datetime):
        return _normalized_timestamp(reference)

    fallback = getattr(monitored, "updated_at", None)
    if isinstance(fallback, datetime):
        return _normalized_timestamp(fallback)

    return None

def _dispatch_comparison_task(
    monitored_id: str | None,
    *,
    db: Session | None,
    price_changed: bool,
    availability_changed: bool,
    source: str,
    task_logger,
) -> None:
    """ Agenda comparação com prioridade alta e garante fallback para ``delay`` """
    if not monitored_id:
        task_logger.info(
            "price_comparison_task_skipped",
            reason="missing_monitored_id",
            source=source,
        )
        return

    try:
        compare_prices_task.apply_async(
            args=(str(monitored_id),),
            queue="compare",
            priority=0,
        )
        task_logger.info(
            "price_comparison_task_dispatched",
            reason="change_detected",
            availability_changed=availability_changed,
            price_changed=price_changed,
            source=source,
        )
    except Exception as exc:
        task_logger.warning(
            "price_comparison_apply_async_failed",
            error=str(exc),
            source=source,
        )
        compare_prices_task.delay(str(monitored_id))

def _mark_failed_product(
    product_reference: str | UUID | None,
    *,
    db: Session | None = None,
    task_logger,
) -> None:
    """ Marca produto como ``failed`` tolerando referências ausentes ou inválidas """
    if not product_reference:
        task_logger.info("mark_failed_skipped", reason="missing_reference")
        return
    
    try:
        product_uuid = product_reference if isinstance(product_reference, UUID) else UUID(str(product_reference))
    except (TypeError, ValueError) as exc:
        task_logger.warning("mark_failed_invalid_reference", error=str(exc), product_id=product_reference)
        return
    
    try:
        if db is None:
            with SessionLocal() as session:
                if not hasattr(session, "query"):
                    task_logger.info("mark_failed_skipped", reason="session_without_query")
                    return
                mark_monitored_product_failed(session, product_uuid)
        else:
            if not hasattr(db, "query"):
                task_logger.info("mark_failed_skipped", reason="session_without_query")
                return
            mark_monitored_product_failed(db, product_uuid)
        task_logger.info("monitored_marked_failed", product_id=str(product_uuid))
    except Exception as exc:
        task_logger.warning("mark_failed_persuist_error", error=str(exc), product_id=str(product_uuid))

def _register_scraping_error(
    db: Session,
    product_reference: str | UUID | None,
    url: str,
    message: str,
    error_type: ScrapingErrorType,
    *,
    task_logger,
) -> None:
    """ Registra ``ScrapingError`` evitando duplicidade e cuidando do primeiro scraping """
    #Garante que apenas IDs válidos gerem registros, evitando ruído no primeiro scraping
    if not product_reference:
        task_logger.info("scraping_error_skipped_no_product", url=url)
        return
    
    try:
        product_uuid = product_reference if isinstance(product_reference, UUID) else UUID(str(product_reference))
    except (TypeError, ValueError) as exc:
        task_logger.warning("scraping_error_invalid_product", error=str(exc), product_id=product_reference)
        return
    
    try:
        crud_errors.create_scraping_error(
            db,
            product_uuid,
            url,
            message,
            error_type,
        )
    except Exception as err:
        task_logger.warning("error_persist_failed", error=str(err))

def _result_value(result: ScrapeResult | Mapping[str, Any] | Any, attr: str, default: Any = None) -> Any:
    """ Extrai atributos de ``ScrapeResult`` aceitando também mapeamentos """
    if hasattr(result, attr):
        return getattr(result, attr)
    if isinstance(result, Mapping):
        return result.get(attr, default)
    return default


def _result_status(result: ScrapeResult | Mapping[str, Any] | Any) -> str:
    """ Obtém status padronizado do retorno do serviço de scraping """
    status_value = _result_value(result, "status")
    if status_value is None:
        return "unknown"
    return str(status_value)


def _result_price_changed(result: ScrapeResult | Mapping[str, Any] | Any) -> bool:
    """ Determina se houve alteração de preço considerando legados """
    changed = _result_value(result, "price_changed")
    if changed is None:
        return _result_status(result) == "success"
    return bool(changed)

def _result_availability_changed(result: ScrapeResult | Mapping[str, Any] | Any) -> bool:
    """ Determina se houve mudança de disponibilidade, considerando defaults """
    changed = _result_value(result, "availability_changed")
    if changed is None:
        return False
    return bool(changed)

def _result_product_id(result: ScrapeResult | Mapping[str, Any] | Any) -> str | None:
    """ Normaliza o identificador de produto retornado pelo scraper """
    value = _result_value(result, "product_id")
    if value is None:
        return None
    return str(value)

def _observe_metrics(start: datetime, task_name: str, status: str) -> None:
    """ Registra latência e contagem de tasks no Prometheus """
    duration = (datetime.now(timezone.utc) - start).total_seconds()
    SCRAPING_LATENCY_SECONDS.labels(source="scraper").observe(duration)

def _compute_retry_delay(base: float, attempt: int, limit: int) -> int:
    """ Calcula atraso exponencial limitado para retries no Celery """
    delay = base * (2 ** max(0, attempt - 1))
    return min(int(delay), limit)

@celery_app.task(
    bind=True,
    max_retries=3,
    default_retry_delay=30,
    name="collect_product_task",
    rate_limit=settings.SCRAPER_RATE_LIMIT,
    queue="scraping",
    acks_late=True,
    reject_on_worker_lost=True,
)
def collect_product_task(
    self,
    payload: Mapping[str, Any] | str | None = None,
    user_id: str | None = None,
    name_identification: str | None = None,
    monitored_id: str | None = None,
    **legacy_kwargs,
) -> None:
    """ Coleta dados de um produto monitorado e os salva no banco """
    payload_source: Mapping[str, Any] | None
    if isinstance(payload, Mapping):
        payload_source = payload
    else:
        payload_source = {
            "url": payload,
            "owner_id": user_id,
            "name": name_identification,
            "monitored_id": monitored_id,
        }

    merged_payload = _merge_payload(
        payload_source,
        {
            "user_id": user_id,
            "name_identification": name_identification,
            "monitored_id": monitored_id,
            **legacy_kwargs,
        },
    )
    url = merged_payload.get("url")
    user_id = merged_payload.get("owner_id")
    name_identification = merged_payload.get("name")
    monitored_id = merged_payload.get("monitored_id")
    request_id = merged_payload.get("request_id")

    SCRAPER_IN_FLIGHT.inc()
    task_logger = logger.bind(
        task_id=self.request.id,
        url=url,
        user_id=user_id,
        monitored_id=monitored_id,
        request_id=request_id,
    )

    start = datetime.now(timezone.utc)
    status = "success"
    task_logger.info("collect_product_started")

    if not url or not user_id:
        status = "failure"
        task_logger.error("missing_payload_fields")
        _observe_metrics(start, "collect_product_task", status)
        SCRAPER_IN_FLIGHT.dec()
        return

    #Verifica se há suspensão global para interromper o fluxo imediatamente
    if is_scraping_suspended():
        status = "failure"
        task_logger.warning("suspended_via_flag", detail="scraping suspended flag is set")
        _observe_metrics(start, "collect_product_task", status)
        SCRAPER_IN_FLIGHT.dec()
        return
    
    if not _acquire_request_guard(str(request_id) if request_id else None, task_logger=task_logger):
        _observe_metrics(start, "collect_product_task", status)
        SCRAPER_IN_FLIGHT.dec()
        return
    
    product_id: str | None = monitored_id

    try:
        normalized_url = normalize_product_url(url)
    except ValueError as exc:
        status = "failure"
        task_logger.exception("invalid_url_payload")
        _mark_failed_product(product_id, task_logger=task_logger)
        _observe_metrics(start, "collect_product_task", status)
        SCRAPER_IN_FLIGHT.dec()
        return
    
    task_logger = task_logger.bind(url=normalized_url)

    #Prepara payload com valores normalizados para schema Pydantic
    try:
        payload_data = {
            "product_url": normalized_url,
        }
        if name_identification is not None:
            payload_data["name_identification"] = name_identification

        payload = MonitoredProductCreateScraping.model_validate(payload_data)
    except Exception as exc:
        status = "failure"
        task_logger.exception("invalid_payload")
        _mark_failed_product(product_id, task_logger=task_logger)
        _observe_metrics(start, "collect_product_task", status)
        SCRAPER_IN_FLIGHT.dec()
        return

    #Execução do scraping delegada ao serviço especializado
    with SessionLocal() as db:
        try:
            user_uuid = UUID(user_id)
        except (TypeError, ValueError) as exc:
            status = "failure"
            task_logger.exception("invalid_user_reference")
            _mark_failed_product(product_id, task_logger=task_logger)
            _observe_metrics(start, "collect_product_task", status)
            SCRAPER_IN_FLIGHT.dec()
            return
        
        existing = None
        if hasattr(db, "query"):
            existing = get_monitored_product_by_user_and_url(db, user_uuid, normalized_url)
        else:
            task_logger.info("monitored_lookup_skipped", reason="session_without_query")
        if existing and monitored_id and str(existing.id) != str(monitored_id):
            task_logger.info(
                "monitored_reference_reconciled",
                provided_id=monitored_id,
                existing_id=str(existing.id),
            )
            product_id = str(existing.id)
        elif existing and not monitored_id:
            task_logger.info(
                "monitored_reference_resolved",
                existing_id=str(existing.id),
            )
            product_id = str(existing.id)
        
        reference = _extract_comparison_reference(db, product_id or monitored_id)
        idempotency_key = _build_idempotency_key(product_id or monitored_id, reference=reference)
        if not _acquire_idempotency_slot(idempotency_key, task_logger=task_logger):
            _observe_metrics(start, "collect_product_task", status)
            SCRAPER_IN_FLIGHT.dec()
            return

        try:
            result: ScrapeResult = scrape_monitored_product(
                db=db,
                url=normalized_url,
                user_id=user_uuid,
                payload=payload,
            )
            product_id = _result_product_id(result) or monitored_id
            status_value = _result_status(result)
            price_changed = _result_price_changed(result)
            availability_changed = _result_availability_changed(result)

            if status_value == "no_result":
                status = "failure"
                task_logger.warning("collect_product_no_result")
                _register_scraping_error(
                    db,
                    product_id,
                    normalized_url,
                    "pipeline retornou no_result",
                    ScrapingErrorType.no_result,
                    task_logger=task_logger,
                )
                retry_delay = min(
                    settings.SCRAPER_NO_RESULT_RETRY_SECONDS * (self.request.retries + 1),
                    settings.SCRAPER_MAX_RETRY_DELAY_SECONDS,
                )
                raise self.retry(countdown=retry_delay)

            elapsed_ms = int((datetime.now(timezone.utc) - start).total_seconds() * 1000)
            task_logger.info(
                "collect_product_completed",
                duration_ms=elapsed_ms,
                status=status_value,
                price_changed=price_changed,
                availability_changed=availability_changed,
            )
            client = _redis_client()
            if client is not None:
                client.set("beat:last_success", datetime.now(timezone.utc).isoformat())

            if price_changed or availability_changed:
                _dispatch_comparison_task(
                    product_id,
                    db=db,
                    price_changed=bool(price_changed),
                    availability_changed=bool(availability_changed),
                    source="monitored_scrape",
                    task_logger=task_logger,
                )

        except ScraperClientError as req_err:
            status = "failure"
            SCRAPER_HEAD_FAILURES_TOTAL.inc()
            task_logger.exception(
                "collect_product_http_error",
                monitored_product_id=product_id,
                url=normalized_url,
                status_code=req_err.status_code,
            )
            _register_scraping_error(
                db,
                product_id,
                normalized_url,
                str(req_err),
                ScrapingErrorType.http_error,
                task_logger=task_logger,
            )
            
            if req_err.status_code and 500 <= req_err.status_code < 600:
                delay = _compute_retry_delay(
                    settings.SCRAPER_RETRY_BACKOFF_MIN,
                    self.request.retries + 1,
                    settings.SCRAPER_MAX_RETRY_DELAY_SECONDS,
                )
                raise self.retry(countdown=delay)
            
            if req_err.status_code == 429 and req_err.retry_after:
                raise self.retry(countdown=req_err.retry_after)
            
            _mark_failed_product(product_id, db=db, task_logger=task_logger)
            raise ScraperError(status_code=req_err.status_code or 500, detail=str(req_err))
        except self.MaxRetriesExceededError as exc:
            status = "failure"
            task_logger.exception("max_retries_exceeded")
            _mark_failed_product(product_id, db=db, task_logger=task_logger)
        except Exception as exc:
            status = "failure"
            task_logger.exception("collect_product_failed")
            _register_scraping_error(
                db,
                product_id,
                normalized_url,
                str(exc),
                ScrapingErrorType.parsing_error,
                task_logger=task_logger,
            )
            _mark_failed_product(product_id, db=db, task_logger=task_logger)
        finally:
            _observe_metrics(start, "collect_product_task", status)
            SCRAPER_IN_FLIGHT.dec()

@celery_app.task(
    bind=True,
    max_retries=3,
    default_retry_delay=30,
    name="collect_competitor_task",
    rate_limit=settings.COMPETITOR_RATE_LIMIT,
    queue="scraping",
    acks_late=True,
    reject_on_worker_lost=True,
)
def collect_competitor_task(
    self,
    payload: Mapping[str, Any] | str | None = None,
    url: str | None = None,
    **legacy_kwargs,
) -> None:
    """ Coleta dados de um produto concorrente e compara os preços.

    Payload mínimo esperado: {monitored_id, competitor_id?, url, owner_id?,
    request_id?}. O contrato antigo (monitored_product_id, url) é suportado
    para transição suave.
    """
    payload_source: Mapping[str, Any] | None
    if isinstance(payload, Mapping):
        payload_source = payload
    else:
        payload_source = {"monitored_id": payload, "url": url}

    merged_payload = _merge_payload(
        payload_source,
        {"url": url, **legacy_kwargs},
    )
    request_id = merged_payload.get("request_id")
    monitored_product_id = merged_payload.get("monitored_id") or merged_payload.get("monitored_product_id")
    url = merged_payload.get("url") or url

    SCRAPER_IN_FLIGHT.inc()
    task_logger = logger.bind(
        task_id=self.request.id,
        monitored_product_id=monitored_product_id,
        url=url,
        request_id=request_id,
    )

    start = datetime.now(timezone.utc)
    status = "success"
    task_logger.info("collect_competitor_started")

    if not url or not monitored_product_id:
        status = "failure"
        task_logger.error("missing_payload_fields")
        _observe_metrics(start, "collect_competitor_task", status)
        SCRAPER_IN_FLIGHT.dec()
        return

    if not _acquire_request_guard(str(request_id) if request_id else None, task_logger=task_logger):
        _observe_metrics(start, "collect_competitor_task", status)
        SCRAPER_IN_FLIGHT.dec()
        return

    #Checa flag de suspensão global antes de gastar recursos
    if is_scraping_suspended():
        task_logger.warning("suspended_via_flag", detail="scraping suspended flag is set")
        status = "failure"
        _observe_metrics(start, "collect_competitor_task", status)
        SCRAPER_IN_FLIGHT.dec()
        return

    try:
        normalized_url = normalize_product_url(url)
    except ValueError as exc:
        status = "failure"
        task_logger.exception("invalid_url_payload")
        _observe_metrics(start, "collect_competitor_task", status)
        SCRAPER_IN_FLIGHT.dec()
        return
    
    task_logger = task_logger.bind(url=normalized_url)

    #Preparação payload a partir dos parâmetros brutos
    try:
        payload = CompetitorProductCreateScraping.model_validate({
            "monitored_product_id": monitored_product_id,
            "product_url": normalized_url
        })
    except Exception as exc:
        status = "failure"
        task_logger.exception("invalid_payload")
        _observe_metrics(start, "collect_competitor_task", status)
        SCRAPER_IN_FLIGHT.dec()
        return

    #Scraping propriamente dito e agendamento de comparação de preços
    with SessionLocal() as db:
        try:
            monitored = None
            if hasattr(db, "query"):
                monitored = get_monitored_product_by_id(db, UUID(monitored_product_id))
            else:
                task_logger.info("competitor_lookup_skipped", reason="session_without_query")
            user_id = monitored.user_id if monitored is not None else UUID(int=0)

            reference = _extract_comparison_reference(db, monitored_product_id)
            idem_key = _build_idempotency_key(monitored_product_id, reference=reference)
            if not _acquire_idempotency_slot(idem_key, task_logger=task_logger):
                _observe_metrics(start, "collect_competitor_task", status)
                SCRAPER_IN_FLIGHT.dec()
                return

            result: ScrapeResult = scrape_competitor_product(
                db=db,
                user_id=user_id,
                url=normalized_url,
                payload=payload,
            )

            status_value = _result_status(result)
            price_changed = _result_price_changed(result)
            availability_changed = _result_availability_changed(result)
            elapsed_ms = int((datetime.now(timezone.utc) - start).total_seconds() * 1000)
            task_logger.info(
                "collect_competitor_completed",
                duration_ms=elapsed_ms,
                status=status_value,
                price_changed=price_changed,
                availability_changed=availability_changed,
            )

            if status_value == "no_result":
                status = "failure"
                _register_scraping_error(
                    db,
                    monitored_product_id,
                    normalized_url,
                    "pipeline retornou no_result",
                    ScrapingErrorType.no_result,
                    task_logger=task_logger,
                )
                delay = min(
                    settings.SCRAPER_NO_RESULT_RETRY_SECONDS * (self.request.retries + 1),
                    settings.SCRAPER_MAX_RETRY_DELAY_SECONDS,
                )
                raise self.retry(countdown=delay)
            
            if price_changed or availability_changed:
                _dispatch_comparison_task(
                    monitored_product_id,
                    db=db,
                    price_changed=bool(price_changed),
                    availability_changed=bool(availability_changed),
                    source="competitor_scrape",
                    task_logger=task_logger,
                )

        except ScraperClientError as req_err:
            status = "failure"
            SCRAPER_HEAD_FAILURES_TOTAL.inc()
            task_logger.exception(
                "collect_competitor_http_error",
                monitored_product_id=monitored_product_id,
                url=normalized_url,
                status_code=req_err.status_code,
            )
            _register_scraping_error(
                db,
                monitored_product_id,
                normalized_url,
                str(req_err),
                ScrapingErrorType.http_error,
                task_logger=task_logger,
            )
            
            if req_err.status_code and 500 <= req_err.status_code < 600:
                delay = _compute_retry_delay(
                    settings.SCRAPER_RETRY_BACKOFF_MIN,
                    self.request.retries + 1,
                    settings.SCRAPER_MAX_RETRY_DELAY_SECONDS,
                )
                raise self.retry(countdown=delay)
            
            if req_err.status_code == 429 and req_err.retry_after:
                raise self.retry(countdown=req_err.retry_after)
            
            raise ScraperError(status_code=req_err.status_code or 500, detail=str(req_err))
        
        except self.MaxRetriesExceededError as exc:
            status = "failure"
            task_logger.exception("max_retries_exceeded")

        except Exception as exc:
            status = "failure"
            task_logger.exception("collect_competitor_failed")

        finally:
            _observe_metrics(start, "collect_competitor_task", status)
            SCRAPER_IN_FLIGHT.dec()
