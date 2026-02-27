""" Avaliador de eventos para geração de candidatos de notificação.

Responsabilidade única: receber snapshots + configurações do usuário
e retornar a lista de NotificationCandidate prontos para persistência.

O que NÃO pertence aqui:
- Deduplicação (está em services_notifications.py + domain/deduplication.py)
- Cooldown (está em services_notifications.py + domain/cooldown_resolver.py)
- Locks Redis (estão em infra/notification_locks.py)
- Persistência (está em crud_notifications.py)
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from decimal import Decimal

import structlog
from sqlalchemy.orm import Session

from market_alert.core.config_alert import settings
from market_alert.models import AlertRule, MonitoredProduct, User, UserNotificationPreference
from market_alert.enums.enums_notifications import EventType, NotificationChannel
from market_alert.notifications.domain.channel_resolver import is_channel_confirmed, resolve_channel_destination
from market_alert.notifications.domain.contact_validator import validate_email, validate_phone_number
from market_alert.notifications.domain.event_detector import detect_events_from_snapshots, map_event_to_alert_type
from market_alert.notifications.domain.price_calculator import is_delta_below_threshold
from market_alert.notifications.domain.snapshot_validator import validate_snapshot_contract
from market_alert.notifications.template_renderer import render_notification


logger = structlog.get_logger("notifications_evaluator")

@dataclass(frozen=True)
class NotificationCandidate:
    """ Representa uma notificação candidata pronta para avaliação pelo service layer.

    Campos essenciais para identificar o destinatário e o conteúdo da mensagem.
    Dedup hash e cooldown_seconds são calculados pela service layer, não aqui.
    """
    channel: NotificationChannel
    event_type: EventType
    payload: dict[str, Any]
    priority: int
    recipient: str
    subject: str | None
    message: str | None
    alert_rule: AlertRule | None = None
    preference: UserNotificationPreference | None = None

def evaluate(
    monitored: MonitoredProduct,
    previous_snapshot: dict[str, Any] | None,
    current_snapshot: dict[str, Any],
    user_prefs: list[UserNotificationPreference],
    *,
    user: User,
    alert_rules: list[AlertRule],
    db: Session | None = None,  # depreciado — não utilizado, será removido na Fase 8
) -> list[NotificationCandidate]:
    """ Avalia snapshots e retorna notificações candidatas por canal.

    Esta função é stateless: não realiza I/O, não verifica cooldown no banco
    e não gera hashes de deduplicação. Essas responsabilidades pertencem
    à service layer (services_notifications.py).

    Args:
        monitored: Produto monitorado que gerou o evento.
        previous_snapshot: Snapshot anterior para comparação (pode ser None).
        current_snapshot: Snapshot atual com os dados mais recentes.
        user_prefs: Preferências de notificação do usuário.
        user: Usuário dono do produto monitorado.
        alert_rules: Regras de alerta configuradas para o usuário.
        db: Depreciado — ignorado. Será removido em versão futura.

    Returns:
        Lista de NotificationCandidate a serem processados pelo service layer.
    """
    if monitored.paused:
        return []

    valid, errors = validate_snapshot_contract(current_snapshot)
    if not valid:
        logger.warning(
            "snapshot_contract_violation",
            label="current_snapshot",
            issues=errors,
        )

    if previous_snapshot is not None:
        valid_prev, errors_prev = validate_snapshot_contract(previous_snapshot)
        if not valid_prev:
            logger.warning(
                "snapshot_contract_violation",
                label="previous_snapshot",
                issues=errors_prev,
            )

    event_types = detect_events_from_snapshots(previous_snapshot, current_snapshot)
    if not event_types:
        return []

    threshold = Decimal(str(settings.MIN_PRICE_DELTA_PERCENT))
    candidates: list[NotificationCandidate] = []

    for event_type in event_types:
        alert_type = map_event_to_alert_type(event_type)
        if alert_type is None:
            continue

        previous_price = (previous_snapshot or {}).get("price")
        current_price = current_snapshot.get("price")
        if event_type == EventType.price_change and is_delta_below_threshold(
            previous_price, current_price, threshold_percent=threshold
        ):
            logger.debug(
                "notification_suppressed_delta_below_threshold",
                monitored_id=str(monitored.id),
                event_type=event_type.value,
            )
            continue

        preferences_by_channel = {
            pref.channel: pref
            for pref in user_prefs
            if pref.enabled and pref.alert_type == alert_type
        }
        rules_by_channel = {
            rule.channel: rule
            for rule in alert_rules
            if rule.alert_type == alert_type
        }

        channels = set(preferences_by_channel.keys()) | set(rules_by_channel.keys())
        if not channels:
            #Fallback para canal email quando não existir configuração explícita
            channels = {NotificationChannel.email}

        for channel in channels:
            preference = preferences_by_channel.get(channel)
            alert_rule_for_channel = rules_by_channel.get(channel)
            if preference and not preference.enabled:
                continue

            recipient = resolve_channel_destination(preference, user=user, channel=channel)
            if not recipient:
                logger.debug(
                    "notification_suppressed_no_recipient",
                    channel=channel.value,
                    monitored_id=str(monitored.id),
                )
                continue

            if channel == NotificationChannel.email:
                if not user.email_verified:
                    continue
                if not validate_email(recipient):
                    continue

            if channel in {NotificationChannel.sms, NotificationChannel.whatsapp}:
                if not validate_phone_number(recipient):
                    continue
                if not is_channel_confirmed(channel=channel, user=user, preference=preference):
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

            from market_alert.notifications.domain.priority_resolver import resolve_priority
            candidates.append(
                NotificationCandidate(
                    channel=channel,
                    event_type=event_type,
                    payload=payload,
                    priority=resolve_priority(alert_rule_for_channel),
                    recipient=recipient,
                    subject=subject,
                    message=message,
                    alert_rule=alert_rule_for_channel,
                    preference=preference,
                )
            )

    logger.info(
        "alert_candidates_created",
        monitored_id=str(monitored.id),
        count=len(candidates),
        channels=[c.channel.value for c in candidates],
        event_types=list({c.event_type.value for c in candidates}),
    )
    return candidates
