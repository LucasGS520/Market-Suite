""" Tarefas de comparação de preços entre produtos monitorados.

Esta task roda de forma assíncrona via Celery. Ela carrega do banco de dados
um produto monitorado e todos os seus concorrentes, executa a comparação de
preços e registra métricas para acompanhamento. O fluxo é roteado para a fila
``compare`` para manter o worker de monitoramento focado no loop contínuo.
"""

import structlog
from uuid import UUID, uuid4
from datetime import datetime, timezone

from shared.infra.db import SessionLocal
from sqlalchemy.orm import Session
from shared.utils.logging_utils import mask_identifier
from shared.metrics.metrics_scraper import SCRAPING_LATENCY_SECONDS
from shared.metrics.metrics_price_comparison import (
    COMPARISON_SKIPPED_PAUSED_TOTAL,
    COMPARE_PRICES_COMPLETED_TOTAL,
    COMPARE_PRICES_STARTED_TOTAL,
    PRICE_COMPARISON_TASK_LATENCY_SECONDS,
)
from shared.metrics.metrics_notifications import (
    NOTIFICATION_ALERTS_CREATED_TOTAL,
    NOTIFICATION_EVENTS_TOTAL,
    NOTIFICATION_IDEMPOTENCY_HITS_TOTAL,
)

from market_alert.core.celery_app import celery_app
from market_alert.core.config_alert import settings
from market_alert.crud.crud_notifications import (
    create_event_log,
    create_notification,
    list_alert_rules,
    list_user_notification_preferences,
    update_alert_rule_last_triggered,
    update_preference_last_notified,
)
from market_alert.enums.enums_notifications import EventType, NotificationStatus
from market_alert.models import MonitoredProduct, PriceHistory, User
from market_alert.notifications.evaluator import evaluate
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
    """ Carrega um produto monitorado e executa a comparação com fluxo enxuto """
    queue_name = (self.request.delivery_info or {}).get("routing_key", "compare")
    task_logger = logger.bind(
        task_id=self.request.id,
        queue=queue_name,
        monitored_id=mask_identifier(monitored_id),
    )
    #Registra a contagem de início para acompanhamento de backlog
    COMPARE_PRICES_STARTED_TOTAL.inc()
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
                #Evita cálculos de comparação quando o monitorado está pausado
                COMPARISON_SKIPPED_PAUSED_TOTAL.inc()
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

            #Log do resultado resumido para fácil consulta
            task_logger.info(
                "compare_prices_completed",
                lowest=result["lowest_competitor"],
                highest=result["highest_competitor"],
            )

        resolved_trace_id = trace_id or self.request.id or str(uuid4())
        #Mantém uma nova sessão para evitar transação aberta da comparação
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
                #Evita emitir eventos de alertas quando o monitorado estiver pausado
                task_logger.info(
                    "compare_prices_notifications_skipped_paused",
                    monitored_id=mask_identifier(monitored_id),
                )
                return
            
            has_price_change = bool(price_changed)
            has_availability_change = bool(availability_changed)
            if not (has_price_change or has_availability_change):
                task_logger.info(
                    "compare_prices_notifications_skipped_no_change",
                    monitored_id=mask_identifier(monitored_id),
                )
                return
            
            price_previous, price_current = _fetch_recent_prices(
                db_notifications,
                monitored.id,
            )
            availability_previous = None
            if availability_changed and monitored.availability is not None:
                # NÃO HÁ HISTÓRICO DE DISPONIBILIDADE, ENTÃO APENAS REGISTRA O VALOR ANTERIOR
                availability_previous = not monitored.availability

            payload_base = {
                "monitored_id": str(monitored.id),
                "monitored_url": monitored.product_url,
                "current_price": str(price_current) if price_current is not None else None,
                "previous_price": str(price_previous) if price_previous is not None else None,
                "availability": monitored.availability,
                "availability_previous": availability_previous,
                "summary": result.get("summary"),
            }
            if price_previous is not None and price_current is not None and price_previous != 0:
                payload_base["price_delta_percent"] = float(
                    ((price_current - price_previous) / price_previous) * 100
                )

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
            
            event_types: list[EventType] = []
            if has_price_change:
                event_types.append(EventType.price_change)
            if has_availability_change:
                event_types.append(EventType.availability_change)

            previous_snapshot = {
                "price": price_previous,
                "availability": availability_previous,
            }
            current_snapshot = {
                "price": price_current,
                "availability": monitored.availability,
                "summary": result.get("summary"),
                "price_delta_percent": payload_base.get("price_delta_percent"),
            }

            preferences = list_user_notification_preferences(
                db_notifications,
                user_id=monitored.user_id,
                monitored_product_id=monitored.id,
            )
            alert_rules = list_alert_rules(
                db_notifications,
                user_id=monitored.user_id,
                monitored_product_id=monitored.id,
            )

            candidates = evaluate(
                monitored,
                previous_snapshot,
                current_snapshot,
                preferences,
                db=db_notifications,
                user=user,
                alert_rules=alert_rules,
            )

            candidates_by_event: dict[EventType, list] = {}
            for candidate in candidates:
                candidates_by_event.setdefault(candidate.event_type, []).append(candidate)

            for event_type in event_types:
                payload = {
                    **payload_base,
                    "event_type": event_type.value,
                }
                notification_ids: list[str] = []
                try:
                    #Evita transação aninhada: SessionLocal já inicia uma transação implícita
                    event = create_event_log(
                        db_notifications,
                        event_type=event_type,
                        trace_id=resolved_trace_id,
                        payload=payload,
                        source="compare_prices_task",
                        monitored_product_id=monitored.id,
                        user_id=user.id,
                        commit=False,
                    )
                    NOTIFICATION_EVENTS_TOTAL.labels(
                        event_type=event_type.value,
                        outcome="evaluated",
                    ).inc()

                    for candidate in candidates_by_event.get(event_type, []):
                        notification = create_notification(
                            db_notifications,
                            event_id=event.id,
                            user_id=monitored.user_id,
                            channel=candidate.channel,
                            recipient=candidate.recipient,
                            dedup_hash=candidate.dedup_hash,
                            event_type=event_type,
                            alert_id=candidate.alert_rule.id if candidate.alert_rule else None,
                            monitored_product_id=monitored.id,
                            subject=candidate.subject,
                            message=candidate.message,
                            payload=candidate.payload,
                            priority=candidate.priority,
                            cooldown_seconds=candidate.cooldown_seconds,
                            status=NotificationStatus.pending,
                            max_attempts=settings.NOTIFICATION_MAX_ATTEMPTS,
                            commit=False,
                        )
                        if notification is None:
                            NOTIFICATION_IDEMPOTENCY_HITS_TOTAL.labels(
                                channel=candidate.channel.value,
                            ).inc()
                            continue
                        notification_ids.append(str(notification.id))
                        NOTIFICATION_ALERTS_CREATED_TOTAL.labels(
                            alert_type=event_type.value,
                            channel=candidate.channel.value,
                        ).inc()

                        if candidate.alert_rule:
                            update_alert_rule_last_triggered(
                                db_notifications,
                                alert_rule=candidate.alert_rule,
                                triggered_at=datetime.now(timezone.utc),
                                commit=False,
                            )
                        if candidate.preference:
                            update_preference_last_notified(
                                db_notifications,
                                preference=candidate.preference,
                                notified_at=datetime.now(timezone.utc),
                                commit=False,
                            )
                    db_notifications.commit()
                except Exception:
                    db_notifications.rollback()
                    raise

                if notification_ids:
                    celery_app.send_task(
                        "market_alert.tasks.notifications_enqueue_task.enqueue_notifications_task",
                        args=[notification_ids],
                        queue="notifications",
                    )
                else:
                    NOTIFICATION_EVENTS_TOTAL.labels(
                        event_type=event_type.value,
                        outcome="no_notifications",
                    ).inc()

    except Exception as exc:
        has_error = True
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
        if not has_error:
            COMPARE_PRICES_COMPLETED_TOTAL.inc()
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
        