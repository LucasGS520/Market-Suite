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

from app.core.celery_app import celery_app
from infra.db import SessionLocal
from app.utils.redis_client import get_redis_client
from app.utils.logging_utils import mask_identifier
from app.services.services_comparison import run_price_comparison
from app.tasks.alert_tasks import send_notification_task
from app.metrics import SCRAPING_LATENCY_SECONDS
from app.core.config import settings


logger = structlog.get_logger("compare_prices")
redis_client = get_redis_client()

@celery_app.task(bind=True, max_retries=3, default_retry_delay=10, name="compare_prices_task", rate_limit=settings.COMPARE_RATE_LIMIT, queue="monitor")
def compare_prices_task(self, monitored_id: str) -> None:
    """ Carrega um produto monitorado e executa a comparação de preços """
    task_logger = logger.bind(task_id=self.request.id, monitored_id=mask_identifier(monitored_id))
    start = datetime.now(timezone.utc)
    status = "success"

    task_logger.info("compare_prices_started")

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

            # Armazena em Redis o timestamp de última comparação bem-sucedida
            redis_client.set(
                f"compare:last_success:{monitored_id}",
                datetime.now(timezone.utc).isoformat(),
                ex=settings.COMPARISON_LAST_SUCCESS_TTL
            )

        except Exception as exc:
            status = "failure"
            task_logger.error("compare_prices_failed", error=str(exc))
            raise self.retry(exc=exc)

        finally:
            #Observa métricas de latência e contagem
            duration = (datetime.now(timezone.utc) - start).total_seconds()
            SCRAPING_LATENCY_SECONDS.labels(source="comparator").observe(duration)
