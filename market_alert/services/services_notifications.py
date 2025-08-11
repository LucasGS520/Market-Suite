""" Serviços relacionados ao envio de alertas

Centraliza funções que utilizam o ``NotificationManager`` para
preparar e disparar alertas aos usuários, evitando duplicações
no projeto
"""

from __future__ import annotations

from datetime import datetime, timezone
from gc import enable
from types import SimpleNamespace

from sqlalchemy.orm import Session

from market_alert.notifications.manager import get_notification_manager, NotificationManager
from market_alert.crud.crud_user import get_user_by_id
from market_alert.crud.crud_alert_rules import get_alert_rules_or_default, update_last_notified
from market_alert.crud.crud_notification_logs import has_recent_duplicate_notification
from market_alert.notifications.matching import alert_matches_rule
from market_alert.notifications.templates import render_price_alert, render_price_change_alert, render_listing_alert, render_error_alert
from market_alert.enums.enums_alerts import AlertType
from market_alert.core.config import settings
from shared import metrics


def dispatch_price_alerts(db: Session | None, monitored_product, alerts: list, manager: NotificationManager | None = None) -> None:
    """ Envia alertas de preço para um produto monitorado

    Caso o usuário tenha notificações habilitadas, aplica regras de alerta,
    evita duplicações recentes e dispara mensagens utilizando o
    ``NotificationManager`` configurado.
    """
    user = get_user_by_id(db, monitored_product.user_id)
    if manager is None:
        manager = get_notification_manager()

    if not getattr(user, "notifications_enabled", True):
        metrics.NOTIFICATIONS_SKIPPED_TOTAL.labels(reason="disabled").inc()
        return

    try:
        rules = get_alert_rules_or_default(db, user.id, monitored_product.id)
    except AttributeError:
        rules = [
            SimpleNamespace(
                id=None,
                rule_type=AlertType.PRICE_TARGET,
                threshold_value=None,
                threshold_percent=None,
                target_price=None,
                product_status=None,
                enabled=True,
                last_notified_at=None
            )
        ]

    now = datetime.now(timezone.utc)
    cooldown = settings.ALERT_RULE_COOLDOWN

    filtered: list[tuple[dict, object]] = []
    for alert in alerts:
        for rule in rules:
            if alert_matches_rule(alert, rule):
                metrics.ALERT_RULES_TRIGGERED_TOTAL.labels(
                    rule_type=rule.rule_type.value
                ).inc()
                last_sent = getattr(rule, "last_notified_at", None)
                if last_sent and (now - last_sent).total_seconds() < cooldown:
                    metrics.ALERT_RULES_SUPPRESSED_TOTAL.labels(
                        reason="cooldown"
                    ).inc()
                    break
                rule_id = str(rule.id) if getattr(rule, "last_notified_at", None) else None
                alert = {**alert, "rule_id": rule_id}
                filtered.append((alert, rule))
                break

    for alert, rule in filtered:
        template = render_price_alert
        alert_type = AlertType.PRICE_TARGET

        if alert.get("type") in ("price_increase", "price_decrease"):
            template = render_price_change_alert
            alert_type = AlertType.PRICE_CHANGE
        elif alert.get("status") in ("unavailable", "removed"):
            template = render_listing_alert
            alert_type = (
                AlertType.LISTING_PAUSED
                if alert.get("status") == "unavailable"
                else AlertType.LISTING_REMOVED
            )
        elif alert.get("error") or alert.get("detail"):
            template = render_error_alert
            alert_type = AlertType.SCRAPING_ERROR

        subject = (
            f"Alerta {alert_type.value.replace('_', ' ')} - "
            f"{monitored_product.name_identification}"
        )
        preview = template(monitored_product, alert)

        duplicate = False
        if db is not None:
            duplicate = has_recent_duplicate_notification(
                db,
                user.id,
                subject,
                preview,
                settings.ALERT_DUPLICATE_WINDOW,
            )
        if not duplicate:
            manager.send_rendered(
                db,
                user,
                subject,
                template,
                monitored_product,
                alert,
                alert_rule_id=alert.get("rule_id"),
                alert_type=alert_type,
            )
            if db is not None:
                update_last_notified(db, alert.get("rule_id"), now)
        else:
            metrics.ALERT_RULES_SUPPRESSED_TOTAL.labels(reason="duplicate").inc()
