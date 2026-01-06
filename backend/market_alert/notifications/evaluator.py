""" Avaliador de eventos para geração de alertas e notificações idempotentes """

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from hashlib import sha256
import json
from typing import Any

import structlog
from sqlalchemy.orm import Session

from shared.metrics.metrics_notifications import (
    NOTIFICATION_ALERTS_SKIPPED_TOTAL,
)
from market_alert.core.config_alert import settings
from market_alert.enums.enums_notifications import AlertType, EventType, NotificationChannel
from market_alert.models import AlertRule, MonitoredProduct, User, UserNotificationPreference
from market_alert.notifications.template_renderer import render_notification
from market_alert.crud.crud_notifications import get_last_sent_at


logger = structlog.get_logger("notifications_evaluator")

@dataclass(frozen=True)
class NotificationCandidate:
    """ Representa uma notificação candidata pronta para persistência """
    channel: NotificationChannel
    event_type: EventType
    payload: dict[str, Any]
    dedup_hash: str
    priority: int
    recipient: str
    subject: str | None
    message: str | None
    cooldown_seconds: int
    alert_rule: AlertRule | None = None
    preference: UserNotificationPreference | None = None

def _resolve_event_types(
    previous_snapshot: dict[str, Any] | None,
    current_snapshot: dict[str, Any],
) -> list[EventType]:
    """ Determina os eventos a partir de mudanças nos snapshots """
    previous_snapshot = previous_snapshot or {}
    event_types: list[EventType] = []

    previous_price = previous_snapshot.get("price")
    current_price = current_snapshot.get("price")
    if previous_price is not None and current_price is not None and previous_price != current_price:
        event_types.append(EventType.price_change)

    previous_availability = previous_snapshot.get("availability")
    current_availability = current_snapshot.get("availability")
    if (
        previous_availability is not None
        and current_availability is not None
        and previous_availability != current_availability
    ):
        event_types.append(EventType.availability_change)

    if current_snapshot.get("competitor_important"):
        event_types.append(EventType.custom)

    return event_types

def _resolve_alert_type(event_type: EventType) -> AlertType | None:
    """ Mapeia evento para tipo de alerta correspondente """
    mapping = {
        EventType.price_change: AlertType.price_change,
        EventType.availability_change: AlertType.availability_change,
        EventType.scraping_error: AlertType.scraping_error,
        EventType.custom: AlertType.custom,
    }
    return mapping.get(event_type)

def _price_delta_below_min(
    previous_price: Any,
    current_price: Any,
) -> bool:
    """ Valida o delta mínimo configurado para alertas de preço """
    if previous_price is None or current_price is None:
        return False
    
    try:
        previous_value = Decimal(str(previous_price))
        current_value = Decimal(str(current_price))
    except (InvalidOperation, TypeError, ValueError):
        return False
    
    if previous_value == 0:
        return False

    delta_percent = abs((current_value - previous_value) / previous_value * previous_value * 100)
    threshold = Decimal(str(settings.MIN_PRICE_DELTA_PERCENT))
    return delta_percent < threshold

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
    if channel in {NotificationChannel.sms, NotificationChannel.whatsapp}:
        return user.phone_number
    
    return None

def _cooldown_seconds(
    *,
    preference: UserNotificationPreference | None,
    alert_rule: AlertRule | None,
) -> int:
    """ Resolve o cooldown final com base em regra, preferência ou default """
    if alert_rule and alert_rule.cooldown_seconds:
        return alert_rule.cooldown_seconds
    if preference and preference.cooldown_seconds:
        return preference.cooldown_seconds
    return settings.DEFAULT_COOLDOWN_SECONDS

def _within_cooldown(
    last_sent_at: datetime | None,
    cooldown_seconds: int,
    *,
    now: datetime,
) -> bool:
    """ Confirma se o cooldown está ativo com base no último envio """
    if last_sent_at is None or cooldown_seconds <= 0:
        return False
    elapsed = (now - last_sent_at).total_seconds()
    return elapsed < cooldown_seconds

def _normalize_payload(payload: dict[str, Any]) -> str:
    """ Normaliza o payload para gerar hash determinístico """
    return json.dumps(payload, sort_keys=True, default=str)

def _build_dedup_hash(
    *,
    monitored_id: str,
    event_type: EventType,
    channel: NotificationChannel,
    payload: dict[str, Any],
) -> str:
    """ Gera hash de deduplicação para eventos equivalentes """
    normalized = _normalize_payload(payload)
    raw = f"{monitored_id}:{event_type.value}:{channel.value}:{normalized}"
    return sha256(raw.encode("utf-8")).hexdigest()

def _resolve_priority(alert_rule: AlertRule | None) -> int:
    """ Define prioridade com base em configuração opcional """
    if alert_rule and isinstance(alert_rule.rule_config, dict):
        priority = alert_rule.rule_config.get("priority")
        if isinstance(priority, int):
            return priority
    return 0

def evaluate(
    monitored: MonitoredProduct,
    previous_snapshot: dict[str, Any] | None,
    current_snapshot: dict[str, Any],
    user_prefs: list[UserNotificationPreference],
    *,
    db: Session,
    user: User,
    alert_rule: list[AlertRule],
) -> list[NotificationCandidate]:
    """ Avalia snapshots e retorna notificações candidatas por canal """
    if monitored.paused:
        NOTIFICATION_ALERTS_SKIPPED_TOTAL.labels(alert_type="paused", reason="monitored_paused").inc()
        return []
    
    event_types = _resolve_event_types(previous_snapshot, current_snapshot)
    if not event_types:
        return []

    now = datetime.now(timezone.utc)
    candidates: list[NotificationCandidate] = []

    for event_type in event_types:
        alert_type = _resolve_alert_type(event_type)
        if alert_type is None:
            continue
        
        previous_price = (previous_snapshot or {}).get("price")
        current_price = current_snapshot.get("price")
        if event_type == EventType.price_change and _price_delta_below_min(previous_price, current_price):
            NOTIFICATION_ALERTS_SKIPPED_TOTAL.labels(alert_type=alert_type.value, reason="delta_below_min").inc()
            continue
        
        preferences_by_channel = {
            pref.channel: pref
            for pref in user_prefs
            if pref.enabled and pref.alert_type == alert_type
        }
        rules_by_channel = {
            rule.channel: rule
            for rule in alert_rule
            if rule.alert_type == alert_type
        }

        channels = set(preferences_by_channel.keys()) | set(rules_by_channel.keys())
        if not channels:
            #Fallback para canal email quando não existir configuração explícita
            channels = {NotificationChannel.email}

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
            last_sent_at = get_last_sent_at(
                db,
                monitored_product_id=monitored.id,
                channel=channel,
            )
            if _within_cooldown(last_sent_at, cooldown_seconds, now=now):
                NOTIFICATION_ALERTS_SKIPPED_TOTAL.labels(alert_type=alert_type.value, reason="cooldown_active").inc()
                continue
            
            context = {
                "alert_type": alert_type.value,
                "event_type": event_type.value,
                "monitored_id": str(monitored.id),
                "monitored_name": monitored.display_name,
                "monitored_url": monitored.product_url,
                "price_current": current_snapshot.get("price"),
                "price_previous": previous_snapshot.get("price") if previous_snapshot else None,
                "price_delta_percent": current_snapshot.get("price_delta_percent"),
                "availability": current_snapshot.get("availability"),
                "availability_previous": previous_snapshot.get("availability") if previous_snapshot else None,
                "summary": current_snapshot.get("summary"),
                "user_name": user.name,
            }
            subject, message = render_notification(
                channel=channel,
                alert_type=alert_type,
                context=context,
            )
            payload = {
                "context": context,
                "subject": subject,
                "message": message,
            }
            dedup_hash = _build_dedup_hash(
                monitored_id=str(monitored.id),
                event_type=event_type,
                channel=channel,
                payload=payload,
            )

            candidates.append(
                NotificationCandidate(
                    channel=channel,
                    event_type=event_type,
                    payload=payload,
                    dedup_hash=dedup_hash,
                    priority=_resolve_priority(alert_rule),
                    recipient=recipient,
                    subject=subject,
                    message=message,
                    cooldown_seconds=cooldown_seconds,
                    alert_rule=alert_rule,
                    preference=preference,
                )
            )

    logger.info(
        "alert_candidates_created",
        monitored_id=str(monitored.id),
        channels=[candidate.channel.value for candidate in candidates],
        event_types=[candidate.event_type.value for candidate in candidates],
    )
    return candidates
