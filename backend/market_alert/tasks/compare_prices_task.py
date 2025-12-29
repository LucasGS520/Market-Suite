""" Tarefas de comparação de preços entre produtos monitorados.

Esta task roda de forma assíncrona via Celery. Ela carrega do banco de dados
um produto monitorado e todos os seus concorrentes, executa a comparação de
preços e registra métricas para acompanhamento. O fluxo foi simplificado para
usar a fila padrão do Celery e evitar coordenação distribuída adicional.
"""

import structlog
from uuid import UUID
from datetime import datetime, timezone

from shared.infra.db import SessionLocal
from shared.utils.logging_utils import mask_identifier
from shared.metrics.metrics_scraper import SCRAPING_LATENCY_SECONDS
from shared.metrics.metrics_price_comparison import (
    PRICE_COMPARISON_TASK_LATENCY_SECONDS,
)

from market_alert.core.celery_app import celery_app
from market_alert.services.services_comparison import run_price_comparison


logger = structlog.get_logger("compare_prices")

@celery_app.task(
    bind=True,
    max_retries=0,
    soft_time_limit=20,
    time_limit=40,
    acks_late=True,
)
def compare_prices_task(self, monitored_id: str) -> None:
    """ Carrega um produto monitorado e executa a comparação com fluxo enxuto """
    task_logger = logger.bind(
        task_id=self.request.id, monitored_id=mask_identifier(monitored_id)
    )
    start = datetime.now(timezone.utc)
    task_logger.info("compare_prices_started")

    with SessionLocal() as db:
        try:
            result = run_price_comparison(db, UUID(monitored_id))

            summary = result.get("summary") or {}
            reason = summary.get("reason")
            if not reason:
                no_competitors = (
                    summary.get("competitors_with_price_count") == 0
                )
                if no_competitors:
                    summary["reason"] = "no_available_competitors"
            if not summary:
                summary = {"reason": "no_available_competitors", "items": []}
            result["summary"] = summary


            #Log do resultado resumido para fácil consulta
            task_logger.info(
                "compare_prices_completed",
                lowest=result["lowest_competitor"],
                highest=result["highest_competitor"],
            )

        except Exception as exc:
            #Log estruturado para acompanhar falhas e motivos antes de propagar
            task_logger.exception(
                "compare_prices_failed",
                product_id=mask_identifier(monitored_id),
                reason=str(exc),
            )
            raise

        finally:
            #Observa métricas de latência e contagem
            duration = (datetime.now(timezone.utc) - start).total_seconds()
            SCRAPING_LATENCY_SECONDS.labels(source="comparator").observe(duration)
            PRICE_COMPARISON_TASK_LATENCY_SECONDS.observe(duration)
        