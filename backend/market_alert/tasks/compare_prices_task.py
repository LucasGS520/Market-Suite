""" Tarefas de comparação de preços entre produtos monitorados.

Esta task roda de forma assíncrona via Celery. Ela carrega do banco de dados
um produto monitorado e todos os seus concorrentes, executa a comparação de
preços e orquestra a geração de notificações via service layer.
O fluxo é roteado para a fila ``compare`` para manter o worker de monitoramento
focado no loop contínuo.
"""

import structlog
from uuid import UUID, uuid4
from datetime import datetime, timezone

from shared.infra.db import SessionLocal
from sqlalchemy.orm import Session
from shared.utils.logging_utils import mask_identifier

from market_alert.core.celery_app import celery_app
from market_alert.models import MonitoredProduct, PriceHistory, User
from market_alert.notifications.services_notifications import evaluate_and_create_notifications
from market_alert.services.services_comparison import run_price_comparison


logger = structlog.get_logger("compare_prices")

@celery_app.task(
    bind=True,
    max_retries=0,
    soft_time_limit=20,
    time_limit=40,
    acks_late=True,
    queue="compare",
)
def compare_prices_task(
    self,
    monitored_id: str,
    price_changed: bool | None = None,
    availability_changed: bool | None = None,
    trace_id: str | None = None,
) -> None:
    """ Carrega um monitorado, compara preços e dispara a avaliação de notificações.

    A task aceita flags opcionais de mudança (`price_changed` e
    `availability_changed`). Quando essas flags não são informadas, o fluxo segue
    mesmo assim para permitir que a camada de notificações avalie o snapshot e
    detecte eventos por conta própria.
    """
    queue_name = (self.request.delivery_info or {}).get("routing_key", "compare")
    task_logger = logger.bind(
        task_id=self.request.id,
        queue=queue_name,
        monitored_id=mask_identifier(monitored_id),
    )
    start = datetime.now(timezone.utc)
    task_logger.info("compare_prices_started")
    has_error = False

    try:
        with SessionLocal() as db:
            monitored = (
                db.query(MonitoredProduct)
                .filter(MonitoredProduct.id == UUID(monitored_id))
                .first()
            )
            if monitored is None:
                task_logger.warning("compare_prices_monitored_missing")
                return

            if monitored.paused:
                task_logger.warning(
                    "compare_prices_skipped_paused",
                    monitored_id=mask_identifier(monitored_id),
                )
                return

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

            task_logger.info(
                "compare_prices_completed",
                lowest=result["lowest_competitor"],
                highest=result["highest_competitor"],
            )

        has_price_change = bool(price_changed) if price_changed is not None else None
        has_availability_change = (
            bool(availability_changed) if availability_changed is not None else None
        )
        if has_price_change is False and has_availability_change is False:
            task_logger.info(
                "compare_prices_notifications_skipped_no_change",
                monitored_id=mask_identifier(monitored_id),
            )
            return

        resolved_trace_id = trace_id or self.request.id or str(uuid4())

        # Nova sessão para evitar transação aberta da comparação
        with SessionLocal() as db_notifications:
            monitored = (
                db_notifications.query(MonitoredProduct)
                .filter(MonitoredProduct.id == UUID(monitored_id))
                .first()
            )
            if monitored is None:
                task_logger.warning("compare_prices_monitored_missing")
                return

            if monitored.paused:
                task_logger.info(
                    "compare_prices_notifications_skipped_paused",
                    monitored_id=mask_identifier(monitored_id),
                )
                return

            user = (
                db_notifications.query(User)
                .filter(User.id == monitored.user_id)
                .first()
            )
            if user is None:
                task_logger.warning(
                    "compare_prices_notifications_missing_user",
                    monitored_id=mask_identifier(monitored_id),
                )
                return

            price_previous, price_current = _fetch_recent_prices(
                db_notifications,
                monitored.id,
            )
            availability_previous = None
            if availability_changed and monitored.availability is not None:
                availability_previous = not monitored.availability

            previous_snapshot = {
                "price": price_previous,
                "availability": availability_previous,
            }
            current_snapshot = {
                "price": price_current,
                "availability": monitored.availability,
                "summary": result.get("summary"),
            }
            if price_previous is not None and price_current is not None and price_previous != 0:
                current_snapshot["price_delta_percent"] = float(
                    ((price_current - price_previous) / price_previous) * 100
                )

            # A camada de serviço concentra as regras de domínio e evita lógica de negócio duplicada na task.
            notification_ids = evaluate_and_create_notifications(
                monitored,
                previous_snapshot,
                current_snapshot,
                user=user,
                db=db_notifications,
                trace_id=resolved_trace_id,
                source="compare_prices_task",
            )

            if notification_ids:
                celery_app.send_task(
                    "market_alert.tasks.notifications_enqueue_task.enqueue_notifications_task",
                    args=[notification_ids],
                    queue="notifications",
                )
                task_logger.info(
                    "compare_prices_notifications_enqueued",
                    count=len(notification_ids),
                )

    except Exception as exc:
        has_error = True
        task_logger.exception(
            "compare_prices_failed",
            product_id=mask_identifier(monitored_id),
            reason=str(exc),
        )
        raise

    finally:
        duration = (datetime.now(timezone.utc) - start).total_seconds()
        task_logger.info(
            "compare_prices_finished",
            status="success" if not has_error else "error",
            duration_seconds=duration,
        )

def _fetch_recent_prices(
    db: Session,
    monitored_id: UUID,
) -> tuple[float | None, float | None]:
    """ Recupera o último e o penúltimo preço para compor payloads de eventos """
    history = (
        db.query(PriceHistory)
        .filter(PriceHistory.monitored_product_id == monitored_id)
        .order_by(PriceHistory.checked_at.desc())
        .limit(2)
        .all()
    )
    if not history:
        return None, None
    current = float(history[0].price) if history[0].price is not None else None
    previous = None
    if len(history) > 1 and history[1].price is not None:
        previous = float(history[1].price)
    return previous, current
