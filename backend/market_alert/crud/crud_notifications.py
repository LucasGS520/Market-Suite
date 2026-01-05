""" Operações CRUD para eventos, alertas e notificações """

from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from sqlalchemy import func
from sqlalchemy.orm import Session
import structlog

from market_alert.enums.enums_notifications import (
    AlertType,
    DeliveryStatus,
    EventType,
    NotificationChannel,
    NotificationStatus,
)
from market_alert.models.models_notifications import (
    AlertRule,
    DeliveryRecord,
    EventLog,
    Notification,
    UserNotificationPreference,
)


logger = structlog.get_logger("crud_notifications")
DEFAULT_MAX_ATTEMPTS = 3

def _normalize_datetime(value: datetime | None) -> datetime:
    """ Normaliza datas para UTC garantindo tzinfo """
    if value is None:
        return datetime.now(timezone.utc)
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)

def create_event_log(
    db: Session,
    *,
    event_type: EventType,
    trace_id: str,
    payload: dict[str, Any],
    source: str | None = None,
    monitored_product_id: UUID | None = None,
    user_id: UUID | None = None,
    occurred_at: datetime | None = None,
    commit: bool = False,
) -> EventLog:
    """ Persiste um evento de domínio de forma imutável """
    normalized_ocurred_at = _normalize_datetime(occurred_at)
    event = EventLog(
        event_type=event_type,
        trace_id=trace_id,
        payload=payload,
        source=source,
        monitored_product_id=monitored_product_id,
        user_id=user_id,
        occurred_at=normalized_ocurred_at,
    )
    db.add(event)
    if commit:
        db.commit()
        db.refresh(event)
    else:
        db.flush()

    logger.info(
        "event_log_created",
        event_id=str(event.id),
        event_type=event_type,
        trace_id=trace_id,
    )
    return event

def create_alert_rule(
    db: Session,
    *,
    user_id: UUID,
    alert_type: AlertType,
    channel: NotificationChannel,
    monitored_product_id: UUID | None = None,
    threshold_value: float | None = None,
    threshold_percent: float | None = None,
    cooldown_seconds: int = 0,
    enabled: bool = True,
    rule_config: dict[str, Any] | None = None,
    commit: bool = False,
) -> AlertRule:
    """ Registra uma regra de alerta configurável """
    rule = AlertRule(
        user_id=user_id,
        monitored_product_id=monitored_product_id,
        alert_type=alert_type,
        channel=channel,
        threshold_value=threshold_value,
        threshold_percent=threshold_percent,
        cooldown_seconds=cooldown_seconds,
        enabled=enabled,
        rule_config=rule_config,
    )
    db.add(rule)
    if commit:
        db.commit()
        db.refresh(rule)
    else:
        db.flush()

    logger.info(
        "alert_rule_created",
        alert_rule_id=str(rule.id),
        user_id=str(user_id),
        alert_type=alert_type,
        channel=channel,
    )
    return rule

def get_notification_by_idempotency_key(db: Session, idempotency_key: str) -> Notification | None:
    """ Recupera notificação pela chave de idempotência """
    return db.query(Notification).filter(Notification.idempotency_key == idempotency_key).first()

def create_notification(
    db: Session,
    *,
    event_id: UUID,
    user_id: UUID,
    channel: NotificationChannel,
    recipient: str,
    idempotency_key: str,
    alert_id: UUID | None = None,
    monitored_product_id: UUID | None = None,
    subject: str | None = None,
    message: str | None = None,
    status: NotificationStatus = NotificationStatus.pending,
    max_attempts: int = DEFAULT_MAX_ATTEMPTS,
    next_attempt_at: datetime | None = None,
    commit: bool = False,
) -> Notification:
    """ Persiste uma notificação pendente respeitando idempotência """
    existing = get_notification_by_idempotency_key(db, idempotency_key)
    if existing:
        return existing
    
    notification = Notification(
        event_id=event_id,
        alert_id=alert_id,
        user_id=user_id,
        monitored_product_id=monitored_product_id,
        channel=channel,
        recipient=recipient,
        subject=subject,
        message=message,
        status=status,
        idempotency_key=idempotency_key,
        max_attempts=max_attempts,
        next_attempt_at=_normalize_datetime(next_attempt_at) if next_attempt_at else None,
    )
    db.add(notification)
    if commit:
        db.commit()
        db.refresh(notification)
    else:
        db.flush()

    logger.info(
        "notification_created",
        notification_id=str(notification.id),
        event_id=str(event_id),
        channel=channel,
        recipient=recipient,
    )
    return notification

def update_notification_status(
    db: Session,
    *,
    notification: Notification,
    status: NotificationStatus,
    attempts: int | None = None,
    last_attempt_at: datetime | None = None,
    next_attempt_at: datetime | None = None,
    sent_at: datetime | None = None,
    commit: bool = False,
) -> Notification:
    """ Atualiza status e timestamps de uma notificação """
    notification.status = status
    if attempts is not None:
        notification.attempts = attempts
    if last_attempt_at is not None:
        notification.last_attempt_at = _normalize_datetime(last_attempt_at)
    if next_attempt_at is not None:
        notification.next_attempt_at = _normalize_datetime(next_attempt_at)
    if sent_at is not None:
        notification.sent_at = _normalize_datetime(sent_at)

    if commit:
        db.commit()
        db.refresh(notification)
    else:
        db.flush()

    logger.info(
        "notification_status_updated",
        notification_id=str(notification.id),
        status=status,
    )
    return notification

def create_delivery_record(
    db: Session,
    *,
    notification_id: UUID,
    attempt_number: int,
    status: DeliveryStatus,
    provider_response: dict[str, Any] | None = None,
    error_message: str | None = None,
    latency_ms: int | None = None,
    delivered_at: datetime | None = None,
    commit: bool = False,
) -> DeliveryRecord:
    """ Registra uma tentativa de entrega para auditoria """
    record = DeliveryRecord(
        notification_id=notification_id,
        attempt_number=attempt_number,
        status=status,
        provider_response=provider_response,
        error_message=error_message,
        latency_ms=latency_ms,
        delivered_at=_normalize_datetime(delivered_at) if delivered_at else None,
    )
    db.add(record)
    if commit:
        db.commit()
        db.refresh(record)
    else:
        db.flush()

    logger.info(
        "delivery_record_created",
        delivery_record_id=str(record.id),
        notification_id=str(notification_id),
        status=status,
    )
    return record

def upsert_user_notification_preference(
    db: Session,
    *,
    user_id: UUID,
    alert_type: AlertType,
    channel: NotificationChannel,
    monitored_product_id: UUID | None = None,
    destination: str | None = None,
    enabled: bool = True,
    cooldown_seconds: int = 0,
    channel_metadata: dict[str, Any] | None = None,
    commit: bool = False,
) -> UserNotificationPreference:
    """ Cria ou atualiza preferências de notificação do usuário """
    preference = (
        db.query(UserNotificationPreference)
        .filter(
            UserNotificationPreference.user_id == user_id,
            UserNotificationPreference.monitored_product_id == monitored_product_id,
            UserNotificationPreference.alert_type == alert_type,
            UserNotificationPreference.channel == channel,
        )
        .first()
    )

    if preference:
        preference.destination = destination
        preference.enabled = enabled
        preference.cooldown_seconds = cooldown_seconds
        preference.channel_metadata = channel_metadata
    else:
        preference = UserNotificationPreference(
            user_id=user_id,
            monitored_product_id=monitored_product_id,
            alert_type=alert_type,
            channel=channel,
            destination=destination,
            enabled=enabled,
            cooldown_seconds=cooldown_seconds,
            channel_metadata=channel_metadata,
        )
        db.add(preference)

    if commit:
        db.commit()
        db.refresh(preference)
    else:
        db.flush()

    logger.info(
        "user_notification_preference_upserted",
        preference_id=str(preference.id),
        user_id=str(user_id),
        alert_type=alert_type,
        channel=channel,
    )
    return preference

def list_notifications_for_user(
    db: Session,
    *,
    user_id: UUID,
    page: int = 1,
    per_page: int = 25,
) -> tuple[list[Notification], int]:
    """ Retorna notificações paginadas por usuário """
    if page < 1:
        page = 1
    if per_page < 1:
        per_page = 25

    query = db.query(Notification).filter(Notification.user_id == user_id)
    total = query.with_entities(func.count(Notification.id)).scalar() or 0
    items = (
        query.order_by(Notification.created_at.desc())
        .offset((page - 1) * per_page)
        .limit(per_page)
        .all()
    )
    return items, total

def list_user_notification_preferences(
    db: Session,
    *,
    user_id: UUID,
    monitored_product_id: UUID | None = None,
    alert_type: AlertType | None = None,
) -> list[UserNotificationPreference]:
    """ Lista preferências de notificação filtrando por usuário e contexto opcional """
    query = db.query(UserNotificationPreference).filter(UserNotificationPreference.user_id == user_id)
    if monitored_product_id is not None:
        query = query.filter(UserNotificationPreference.monitored_product_id == monitored_product_id)
    if alert_type is not None:
        query = query.filter(UserNotificationPreference.alert_type == alert_type)
    return query.order_by(UserNotificationPreference.created_at.desc()).all()

def update_alert_rule_last_triggered(
    db: Session,
    *,
    alert_rule: AlertRule,
    triggered_at: datetime | None = None,
    commit: bool = False,
) -> AlertRule:
    """ Atualiza o carimbo de último disparo da regra de alerta """
    alert_rule.last_triggered_at = _normalize_datetime(triggered_at)
    if commit:
        db.commit()
        db.refresh(alert_rule)
    else:
        db.flush()
    return alert_rule

def update_preference_last_notified(
    db: Session,
    *,
    preference: UserNotificationPreference,
    notified_at: datetime | None = None,
    commit: bool = False,
) -> UserNotificationPreference:
    """ Atualiza o carimbo de última notificação da preferência """
    preference.last_notified_at = _normalize_datetime(notified_at)
    if commit:
        db.commit()
        db.refresh(preference)
    else:
        db.flush()
    return preference
