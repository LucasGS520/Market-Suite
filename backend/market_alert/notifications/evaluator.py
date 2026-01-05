""" Avaliador de eventos para gerar alertas e notificações idempotentes """

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Any

import structlog
from sqlalchemy.orm import Session

from shared.metrics.metrics_notifications import (
    NOTIFICATION_ALERTS_SKIPPED_TOTAL,
)
from market_alert.core.config_alert import settings
from market_alert.enums.enums_notifications import AlertType, EventType, NotificationChannel
from market_alert.models import AlertRule, EventLog, MonitoredProduct, User, UserNotificationPreference
from market_alert.notifications.template_renderer import render_notification
from market_alert.utils.rate_limiter import allow_with_leaky_bucket


logger = structlog.get_logger("notifications_evaluator")

@dataclass(frozen=True)
class AlertSpec:
    """ Resultado de avaliação contendo dados prontos para persistência """
    alert_type: AlertType
    channel: NotificationChannel
    recipient: str
    subject: str | None
    message: str | None
    idempotency_key: str
    cooldown_seconds: int
    alert_rule: AlertRule | None = None
    preference: UserNotificationPreference | None = None

def _map_event_type(event_type: EventType) -> AlertType | None:
    """ Mapeia o tipo de evento para o tipo de alerta correspondente """
    mapping = {
        EventType.price_change: AlertType.price_change,
        EventType.availability_change: AlertType.availability_change,
        EventType.scraping_error: AlertType.Scraping_error,
        EventType.custom: AlertType.custom,
    }
    return mapping.get(event_type)

def _should_skip_due_to_delta(payload: dict[str, Any], alert_type: AlertType) -> bool:
    """ Valida limiar de variação mínima para alertas de preço """
    if alert_type != AlertType.price_change:
        return False
    
    delta_value = payload.get("price_delta_percent")
    if delta_value is None:
        return False
    
    try:
        delta_decimal = Decimal(str(delta_value))
    except (InvalidOperation, TypeError, ValueError):
        return False
    
    threshold = Decimal(str(settings.MIN_PRICE_DELTA_PERCENT))
    if abs(delta_decimal) < threshold:
        NOTIFICATION_ALERTS_SKIPPED_TOTAL.labels(alert_type=alert_type.value, reason="delta_below_min").inc()
        return True
    
    return False

def _resolve_channel_destination(
    preference: UserNotificationPreference | None,
    *,
    user: User,
    channel: NotificationChannel,
) -> str | None:
    """ Determina o destino do canal respeitando preferência e dados do usuário """
    if preference and preference.destination:
        return preference.destination
    
    if channel == NotificationChannel.email:
        return user.email
    if channel == NotificationChannel.sms:
        return user.phone_number
    
    return None

def _cooldown_seconds(
    *,
    preference: UserNotificationPreference | None,
    alert_rule: AlertRule | None,
) -> int:
    """ Resolve o cooldown final a partir de regra, preferência ou default """
    if alert_rule and alert_rule.cooldown_seconds:
        return alert_rule.cooldown_seconds
    if preference and preference.cooldown_seconds:
        return preference.cooldown_seconds
    return settings.DEFAULT_COOLDOWN_SECONDS

def _within_cooldown(
    last_notified_at: datetime | None,
    cooldown_seconds: int,
    *,
    now: datetime,
) -> bool:
    """ Verifica se o cooldown ainda está ativo para o alerta atual """
    if last_notified_at is None or cooldown_seconds <= 0:
        return False
    elapsed = (now - last_notified_at).total_seconds()
    return elapsed < cooldown_seconds

def _allow_throttle(
    *,
    monitored_id: str | None,
    alert_type: AlertType,
    cooldown_seconds: int,
) -> bool:
    """ Aplica throttle distribuído usando o *leaky bucket* do Redis """
    if cooldown_seconds <= 0:
        return True
    bucket_key = f"notifications:cooldown:{monitored_id}:{alert_type.value}"
    return allow_with_leaky_bucket(
        bucket_key,
        rate_limit=(1, cooldown_seconds),
    )

def _load_preferences(
    db: Session,
    *,
    user_id: str,
    monitored_id: str | None,
    alert_type: AlertType,
) -> list[UserNotificationPreference]:
    """ Carrega preferências ativas de notificação do usuário """
    query = db.query(UserNotificationPreference).filter(
        UserNotificationPreference.user_id == user_id,
        UserNotificationPreference.alert_type == alert_type,
    )
    if monitored_id:
        query = query.filter(
            UserNotificationPreference.monitored_product_id == monitored_id
        )
    return query.all()

def _load_alert_rules(
    db: Session,
    *,
    user_id: str,
    monitored_id: str | None,
    alert_type: AlertType,
) -> list[AlertRule]:
    """ Carrega regras de alerta configuradas para o usuário """
    query = db.query(AlertRule).filter(
        AlertRule.user_id == user_id,
        AlertRule.alert_type == alert_type,
        AlertRule.enabled_is_(True),
    )
    if monitored_id:
        query = query.filter(
            AlertRule.monitored_product_id == monitored_id
        )
    return query.all()

def evaluate_event(
    db: Session,
    *,
    event: EventLog,
    user: User,
    monitored: MonitoredProduct | None,
) -> list[AlertSpec]:
    """ Avalia um evento e retorna alertas prontos para persistência """
    alert_type = _map_event_type(event.event_type)
    if alert_type is None:
        return []
    
    if monitored and monitored.paused:
        NOTIFICATION_ALERTS_SKIPPED_TOTAL.labels(alert_type=alert_type.value, reason="monitored_paused").inc()
        return []
    
    payload = event.payload if isinstance(event.payload, dict) else {}
    if _should_skip_due_to_delta(payload, alert_type):
        return []
    
    preferences = _load_preferences(
        db,
        user_id=str(user.id),
        monitored_id=str(monitored.id) if monitored else None,
        alert_type=alert_type,
    )
    rules = _load_alert_rules(
        db,
        user_id=str(user.id),
        monitored_id=str(monitored.id) if monitored else None,
        alert_type=alert_type,
    )

    preferences_by_channel = {pref.channel: pref for pref in preferences if pref.enabled}
    rules_by_channel = {rule.channel: rule for rule in rules}

    channels = set(preferences_by_channel.keys()) | set(rules_by_channel.keys())
    if not channels:
        #Fallback para camal email quando não existir configuração explicita
        channels = {NotificationChannel.email}

    now = datetime.now(timezone.utc)
    results: list[AlertSpec] = []

    for channel in channels:
        preference = preferences_by_channel.get(channel)
        alert_rule = rules_by_channel.get(channel)
        if preference and not preference.enabled:
            NOTIFICATION_ALERTS_SKIPPED_TOTAL.labels(alert_type=alert_type.value, reason="preference_disabled").inc()
            continue
        
        recipient = _resolve_channel_destination(
            preference,
            user=user,
            channel=channel,
        )
        if not recipient:
            NOTIFICATION_ALERTS_SKIPPED_TOTAL.labels(alert_type=alert_type.value, reason="missing_destination").inc()
            continue
        
        cooldown_seconds = _cooldown_seconds(
            preference=preference,
            alert_rule=alert_rule,
        )
        last_notified_at = None
        if preference and preference.last_notified_at:
            last_notified_at = preference.last_notified_at
        if alert_rule and alert_rule.last_triggered_at:
            if last_notified_at is None or alert_rule.last_triggered_at > last_notified_at:
                last_notified_at = alert_rule.last_triggered_at

        if _within_cooldown(last_notified_at, cooldown_seconds, now=now):
            NOTIFICATION_ALERTS_SKIPPED_TOTAL.labels(alert_type=alert_type.value, reason="cooldown_active").inc()
            continue
        
        if not _allow_throttle(
            monitored_id=str(monitored.id) if monitored else None,
            alert_type=alert_type,
            cooldown_seconds=cooldown_seconds,
        ):
            NOTIFICATION_ALERTS_SKIPPED_TOTAL.labels(alert_type=alert_type.value, reason="cooldown_throttle").inc()
            continue
        
        context = {
            "event_id": str(event.id),
            "trace_id": event.trace_id,
            "alert_type": alert_type.value,
            "monitored_id": str(monitored.id) if monitored else None,
            "monitored_name": monitored.display_name if monitored else None,
            "monitored_url": payload.get("monitored_url"),
            "price_current": payload.get("current_price"),
            "price_previous": payload.get("previous_price"),
            "price_delta_percent": payload.get("price_delta_percent"),
            "availability": payload.get("availability"),
            "availability_previous": payload.get("availability_previous"),
            "summary": payload.get("summary"),
            "user_name": user.name,
        }
        subject, message = render_notification(
            channel=channel,
            alert_type=alert_type,
            context=context,
        )
        idempotency_key = f"{event.id}:{recipient}:{channel.value}"

        results.append(
            AlertSpec(
                alert_type=alert_type,
                channel=channel,
                recipient=recipient,
                subject=subject,
                message=message,
                idempotency_key=idempotency_key,
                cooldown_seconds=cooldown_seconds,
                alert_rule=alert_rule,
                preference=preference,
            )
        )

    logger.info(
        "alert_evaluated",
        event_id=str(event.id),
        alert_type=alert_type.value,
        channels=[spec.channel.value for spec in results],
    )
    return results
