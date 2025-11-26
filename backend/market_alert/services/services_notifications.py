""" Serviços relacionados ao envio de alertas

Centraliza funções que utilizam o ``NotificationManager`` para
preparar e disparar alertas aos usuários, evitando duplicações
no projeto
"""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID
from types import SimpleNamespace

from sqlalchemy.orm import Session

from market_alert.notifications.manager import get_notification_manager, NotificationManager
from market_alert.crud.crud_user import get_user_by_id
from market_alert.crud.crud_alert_rules import get_alert_rules_or_default, update_last_notified
from market_alert.crud.crud_notification_logs import (
    get_notification_logs,
    has_recent_duplicate_notification,
)
from market_alert.notifications.matching import alert_matches_rule
from market_alert.notifications.templates import render_price_alert, render_price_change_alert, render_listing_alert, render_error_alert
from market_alert.enums.enums_alerts import AlertType, ChannelType
from market_alert.core.config_alert import settings
from shared import metrics


def filter_alerts_by_rules(
    alerts: list, rules: list, cooldown: int, now: datetime | None = None
) -> list[tuple[dict, object]]:
    """ Filtra alertas com base nas regras configuradas """
    if now is None:
        now = datetime.now(timezone.utc)

    filtrados: list[tuple[dict, object]] = []
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
                filtrados.append((alert, rule))
                break
    return filtrados

def is_duplicate_notification(
    db:Session | None, user_id: int, subject: str, preview: str
) -> bool:
    """ Verifica se já existe uma notificação idêntica recente """
    if db is None:
        return False
    return has_recent_duplicate_notification(
        db,
        user_id,
        subject,
        preview,
        settings.ALERT_DUPLICATE_WINDOW,
    )

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
                rule_type=AlertType.PRICE_CHANGE,
                product_status=None,
                enabled=True,
                last_notified_at=None
            )
        ]

    now = datetime.now(timezone.utc)
    filtered = filter_alerts_by_rules(
        alerts, rules, settings.ALERT_RULE_COOLDOWN, now
    )

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

        duplicate = is_duplicate_notification(db, user.id, subject, preview)
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
                #Apenas atualiza a data da regra quando houver identificador válido
                if alert.get("rule_id"):
                    update_last_notified(db, alert.get("rule_id"), now)
        else:
            metrics.ALERT_RULES_SUPPRESSED_TOTAL.labels(reason="duplicate").inc()

def list_notification_logs_for_user(
    *,
    db: Session,
    user_id: UUID,
    limit: int = 20,
    offset: int = 0,
    start: datetime | None = None,
    end: datetime | None = None,
    channel: ChannelType | None = None,
    success: bool | None = None,
    alert_rule_id: UUID | None = None,
    cursor: datetime | None = None,
):
    """Recupera logs filtrados de notificações para um usuário autenticado."""

    return get_notification_logs(
        db,
        user_id,
        limit=limit,
        offset=offset,
        start=start,
        end=end,
        channel=channel,
        success=success,
        alert_rule_id=alert_rule_id,
        cursor=cursor,
    )
