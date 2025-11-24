"""Tarefas de comparação de preços entre produtos monitorados.

Esta task roda de forma assíncrona via Celery. Ela carrega do banco de dados
um produto monitorado e todos os seus concorrentes, executa a comparação de
preços e registra métricas para acompanhamento. O fluxo foi simplificado para
usar a fila padrão do Celery e evitar coordenação distribuída adicional.
"""

import structlog
from uuid import UUID
from datetime import datetime, timezone
from decimal import Decimal

from shared.infra.db import SessionLocal
from shared.utils.logging_utils import mask_identifier
from shared.metrics.metrics_scraper import SCRAPING_LATENCY_SECONDS
from shared.metrics.metrics_price_comparison import (
    PRICE_COMPARISON_TASK_LATENCY_SECONDS,
)
from shared.infra.redis_pubsub import publish_message

from market_alert.core.celery_app import celery_app
from market_alert.services.services_comparison import run_price_comparison
from market_alert.tasks.alert_tasks import send_notification_task
from market_alert.core.config_alert import settings


logger = structlog.get_logger("compare_prices")

@celery_app.task(
    bind=True,
    max_retries=3,
    default_retry_delay=10,
    name="compare_prices_task",
    soft_time_limit=20,
    time_limit=40,
    acks_late=True,
)
def compare_prices_task(self, monitored_id: str) -> None:
    """Carrega um produto monitorado e executa a comparação com fluxo enxuto."""
    task_logger = logger.bind(
        task_id=self.request.id, monitored_id=mask_identifier(monitored_id)
    )
    start = datetime.now(timezone.utc)
    task_logger.info("compare_prices_started")

    with SessionLocal() as db:
        try:
            #Executa a comparação via serviço dedicado
            result, alerts = run_price_comparison(
                db,
                UUID(monitored_id),
                tolerance=Decimal(str(settings.PRICE_TOLERANCE)),
            )

            # Log do resultado resumido para fácil consulta
            task_logger.info(
                "compare_prices_completed",
                lowest=result["lowest_competitor"],
                highest=result["highest_competitor"],
                alerts_count=len(alerts),
            )

            _dispatch_realtime_event(
                result,
                alerts,
                task_id=getattr(self.request, "id", None),
            )

            if alerts:
                send_notification_task.delay(monitored_id, alerts)

        except Exception as exc:
            task_logger.exception("compare_prices_failed")
            raise self.retry(exc=exc)

        finally:
            #Observa métricas de latência e contagem
            duration = (datetime.now(timezone.utc) - start).total_seconds()
            SCRAPING_LATENCY_SECONDS.labels(source="comparator").observe(duration)
            PRICE_COMPARISON_TASK_LATENCY_SECONDS.observe(duration)

def _dispatch_realtime_event(
    result: dict,
    alerts: list,
    *,
    task_id: str | None,
) -> None:
    """Publica evento no Redis com dados da comparação recém-criada."""

    monitored_id = result.get("monitored_id")
    user_id = result.get("user_id")
    comparison_id = result.get("comparison_id")
    summary = result.get("summary")

    channels: list[str] = []
    if isinstance(user_id, str) and user_id:
        channels.append(f"user:{user_id}")
    if isinstance(monitored_id, str) and monitored_id:
        channels.append(f"monitored:{monitored_id}")

    if not channels or not isinstance(comparison_id, str) or not comparison_id:
        return

    event_payload = {
        "type": "comparison.created",
        "monitored_id": monitored_id,
        "comparison_id": comparison_id,
        "summary": summary,
        "alerts": alerts,
        "task_id": task_id,
        "trace_id": task_id,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "channels": channels,
        "user_id": user_id,
    }

    published = publish_message("notifications", event_payload)
    if not published:
        logger.warning(
            "compare_prices_realtime_failed",
            monitored_id=mask_identifier(monitored_id) if monitored_id else None,
        )
        