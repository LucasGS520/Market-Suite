""" Tarefas de comparação de preços entre produtos monitorados.

Esta task roda de forma assíncrona via Celery. Ela delega comparação ao
service layer, avalia notificações e enfileira o envio. Opera em sessão
única — run_price_comparison commita internamente, permitindo reuso seguro.
"""

import structlog

from uuid import UUID, uuid4
from datetime import datetime, timezone

from shared.infra.db import SessionLocal
from shared.utils.trace_context import set_trace_id
from shared.utils.logging_utils import mask_identifier

from market_alert.core.celery_app import celery_app
from market_alert.core.retry_policies import COMPARISON_RETRY
from market_alert.crud import crud_price_history
from market_alert.crud.crud_monitored import get_monitored_product_by_id
from market_alert.crud.crud_user import get_user_by_id
from market_alert.notifications.services_notifications import enqueue_pending_notifications, evaluate_and_create_notifications
from market_alert.comparisons.services.services_comparison import run_price_comparison


logger = structlog.get_logger("compare_prices")


@celery_app.task(
    bind=True,
    queue="compare",
    **COMPARISON_RETRY,
)
def compare_prices_task(
    self,
    monitored_id: str,
    price_changed: bool | None = None,
    availability_changed: bool | None = None,
    trace_id: str | None = None,
) -> None:
    """ Compara preços e dispara avaliação de notificações para um monitorado.

    Aceita flags opcionais de mudança. Quando não informadas, a camada de
    notificações avalia o snapshot por conta própria. Pré-condições (paused,
    inativo) são tratadas pelo service — a task não precisa verificá-las.
    """
    set_trace_id(trace_id or self.request.id or str(uuid4()))
    task_logger = logger.bind(
        task_id=self.request.id,
        queue=(self.request.delivery_info or {}).get("routing_key", "compare"),
        monitored_id=mask_identifier(monitored_id),
    )
    start = datetime.now(timezone.utc)
    task_logger.info("compare_prices_started")
    has_error = False

    try:
        with SessionLocal() as db:
            result = run_price_comparison(db, UUID(monitored_id))

            summary = result.get("summary") or {}
            if not summary.get("reason") and summary.get("competitors_with_price_count") == 0:
                summary["reason"] = "no_available_competitors"
            if not summary:
                summary = {"reason": "no_available_competitors", "items": []}
            result["summary"] = summary

            task_logger.info(
                "compare_prices_completed",
                lowest=result["lowest_competitor"],
                highest=result["highest_competitor"],
            )

            # Produto pausado/inativo: service já persistiu stub, não há notificações
            if result.get("summary", {}).get("ignored_due_to_inactive"):
                task_logger.info(
                    "compare_prices_notifications_skipped_inactive",
                    monitored_id=mask_identifier(monitored_id),
                    reason=result["summary"].get("reason"),
                )
                return

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

            # Sessão reutilizada — run_price_comparison já commitou, estado limpo
            monitored = get_monitored_product_by_id(db, UUID(monitored_id))
            if monitored is None:
                task_logger.warning("compare_prices_monitored_missing")
                return

            user = get_user_by_id(db, monitored.user_id)
            if user is None:
                task_logger.warning(
                    "compare_prices_notifications_missing_user",
                    monitored_id=mask_identifier(monitored_id),
                )
                return

            price_previous, price_current = crud_price_history.fetch_recent_prices(
                db, monitored.id
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

            resolved_trace_id = trace_id or self.request.id or str(uuid4())
            notification_ids = evaluate_and_create_notifications(
                monitored,
                previous_snapshot,
                current_snapshot,
                user=user,
                db=db,
                trace_id=resolved_trace_id,
                source="compare_prices_task",
            )
            
            if notification_ids:
                enqueue_pending_notifications(
                    db,
                    notification_ids,
                    trace_id=resolved_trace_id,
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
