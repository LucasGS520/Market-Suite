"""Tarefas de comparação de preços entre produtos monitorados.

Esta task roda de forma assíncrona via Celery. Ela carrega do banco de dados
um produto monitorado e todos os seus concorrentes, executa a comparação de
preços e registra métricas para acompanhamento. O ``rate_limit`` definido no
decorador limita quantas comparações cada worker pode iniciar por minuto e é
independente da lógica que agenda novas verificações.
"""

import structlog
from uuid import UUID
from datetime import datetime, timezone
from decimal import Decimal
from typing import Mapping

from shared.infra.db import SessionLocal
from shared.utils.redis_client import get_redis_client
from shared.utils.logging_utils import mask_identifier
from shared.metrics.metrics_scraper import SCRAPING_LATENCY_SECONDS
from shared.metrics.metrics_price_comparison import (
    PRICE_COMPARISON_TASK_LATENCY_SECONDS,
)

from market_alert.core.celery_app import celery_app
from market_alert.services.services_comparison import run_price_comparison
from market_alert.tasks.alert_tasks import send_notification_task
from market_alert.core.config_alert import settings
from backend.shared.infra.redis import (
    IdempotencyOwnershipError,
    register_idempotency_key,
    store_idempotency_response,
)


logger = structlog.get_logger("compare_prices")
redis_client = get_redis_client()

@celery_app.task(
    bind=True,
    max_retries=3,
    default_retry_delay=10,
    name="compare_prices_task",
    rate_limit=settings.COMPARE_RATE_LIMIT,
    queue="compare",
)
def compare_prices_task(self, monitored_id: str, idempotency_key: str | None = None) -> None:
    """ Carrega um produto monitorado e executa a comparação de preços """
    task_logger = logger.bind(task_id=self.request.id, monitored_id=mask_identifier(monitored_id))
    start = datetime.now(timezone.utc)
    status = "success"

    task_logger.info("compare_prices_started")

    request_headers = getattr(self.request, "headers", {})
    header_key: str | None = None
    if isinstance(request_headers, Mapping):
        #Padroniza leitura do header independente de capitalização
        header_key = request_headers.get("Idempotency-Key") or request_headers.get("idempotency-key")

    effective_key = idempotency_key or header_key
    idempotency_record = None

    if effective_key:
        try:
            idempotency_record = register_idempotency_key(
                namespace="comparison_task",
                key=effective_key,
                owner=str(monitored_id),
                ttl_seconds=settings.COMPARISON_IDEMPOTENCY_TTL_SECONDS,
            )
        except IdempotencyOwnershipError as exc:
            #A rejeição protege contra reprocessamentos concorrentes de outro contexto
            task_logger.warning(
                "compare_prices_idempotency_conflict",
                idempotency_key=effective_key,
                error=str(exc),
            )
            return
        
        if idempotency_record is not None and not idempotency_record.is_new:
            task_logger.info(
                "compare_prices_idempotent_skip",
                idempotency_key=effective_key,
            )
            return

    with SessionLocal() as db:
        try:
            #Executa a comparação via serviço dedicado
            result, alerts = run_price_comparison(
                db,
                UUID(monitored_id),
                tolerance=Decimal(str(settings.PRICE_TOLERANCE)),
                price_change_threshold=Decimal(str(settings.PRICE_CHANGE_THRESHOLD))
            )

            # Log do resultado resumido para fácil consulta
            task_logger.info(
                "compare_prices_completed",
                lowest=result["lowest_competitor"],
                highest=result["highest_competitor"],
                alerts_count=len(alerts)
            )

            if alerts:
                send_notification_task.delay(monitored_id, alerts)

            if idempotency_record is not None and effective_key:
                store_idempotency_response(
                    namespace="comparison_task",
                    key=effective_key,
                    owner=str(monitored_id),
                    ttl_seconds=settings.COMPARISON_IDEMPOTENCY_TTL_SECONDS,
                    response=result,
                    status_code=200,
                )

            #Garante que a persistência no Redis só ocorre quando o cliente estiver disponível
            client = redis_client or get_redis_client()
            if client is not None:
                client.set(
                    f"compare:last_success:{monitored_id}",
                    datetime.now(timezone.utc).isoformat(),
                    ex=settings.COMPARISON_LAST_SUCCESS_TTL,
                )
            else:
                task_logger.warning("compare_prices_redis_unavailable")

        except Exception as exc:
            status = "failure"
            task_logger.error("compare_prices_failed", error=str(exc))
            raise self.retry(exc=exc)

        finally:
            #Observa métricas de latência e contagem
            duration = (datetime.now(timezone.utc) - start).total_seconds()
            SCRAPING_LATENCY_SECONDS.labels(source="comparator").observe(duration)
            PRICE_COMPARISON_TASK_LATENCY_SECONDS.observe(duration)
