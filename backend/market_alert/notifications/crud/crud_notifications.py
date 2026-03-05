""" Operações CRUD para eventos, alertas e notificações.

Este módulo contém apenas operações de persistência e consulta no banco de dados.
Toda lógica de deduplicação, cooldown e locks pertence ao service layer.
"""

from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import UUID

import structlog
from sqlalchemy import and_, func, or_
from sqlalchemy.orm import Session

from market_alert.core.config_alert import settings
from market_alert.models.models_notifications import (
    AlertRule,
    EventLog,
    Notification,
    NotificationAttempt,
    UserNotificationPreference,
)
from market_alert.enums.enums_notifications import (
    AlertType,
    DeliveryStatus,
    EventType,
    NotificationChannel,
    NotificationStatus,
)


logger = structlog.get_logger("crud_notifications")
DEFAULT_MAX_ATTEMPTS = 3
DEFAULT_CHANNEL_SETTINGS = {
    NotificationChannel.email: True,
    NotificationChannel.push: False,
    NotificationChannel.sms: False,
    NotificationChannel.whatsapp: False,
}

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
    normalized_occurred_at = _normalize_datetime(occurred_at)
    event = EventLog(
        event_type=event_type,
        trace_id=trace_id,
        payload=payload,
        source=source,
        monitored_product_id=monitored_product_id,
        user_id=user_id,
        occurred_at=normalized_occurred_at,
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

def has_recent_sent_notification(
    db: Session,
    *,
    dedup_hash: str,
    window_seconds: int,
    now: datetime,
) -> bool:
    """ Verifica se houve envio recente com o mesmo dedup_hash dentro da janela.

    Args:
        db: Sessão do banco de dados.
        dedup_hash: Hash de deduplicação da notificação.
        window_seconds: Tamanho da janela de verificação em segundos.
        now: Instante de referência para o cálculo.

    Returns:
        True se existe notificação enviada dentro da janela.
    """
    window_start = now - timedelta(seconds=window_seconds)
    existing = (
        db.query(Notification.id)
        .filter(
            Notification.dedup_hash == dedup_hash,
            Notification.status == NotificationStatus.sent,
            Notification.sent_at.is_not(None),
            Notification.sent_at >= window_start,
        )
        .first()
    )
    return existing is not None

def has_dedup_in_window(
    db: Session,
    *,
    dedup_hash: str,
    cooldown_seconds: int,
    now: datetime,
) -> bool:
    """ Verifica se existe notificação duplicada no banco dentro da janela de cooldown.

    Args:
        db: Sessão do banco de dados.
        dedup_hash: Hash de deduplicação da notificação.
        cooldown_seconds: Tamanho da janela em segundos.
        now: Instante de referência para o cálculo.

    Returns:
        True se existe duplicata dentro da janela (pending, processing ou sent).
    """
    if cooldown_seconds <= 0:
        return False
    window_start = now - timedelta(seconds=cooldown_seconds)
    existing = (
        db.query(Notification.id)
        .filter(
            Notification.dedup_hash == dedup_hash,
            Notification.created_at >= window_start,
            Notification.status.in_(
                [NotificationStatus.pending, NotificationStatus.processing, NotificationStatus.sent]
            ),
        )
        .first()
    )
    return existing is not None

def create_notification(
    db: Session,
    *,
    event_id: UUID,
    user_id: UUID,
    channel: NotificationChannel,
    recipient: str,
    dedup_hash: str,
    event_type: EventType,
    alert_id: UUID | None = None,
    monitored_product_id: UUID | None = None,
    subject: str | None = None,
    message: str | None = None,
    payload: dict[str, Any] | None = None,
    priority: int = 0,
    cooldown_seconds: int = 0,
    status: NotificationStatus = NotificationStatus.pending,
    max_attempts: int = DEFAULT_MAX_ATTEMPTS,
    next_attempt_at: datetime | None = None,
    commit: bool = False,
) -> Notification:
    """ Persiste uma notificação pendente no banco de dados.

    Esta função apenas cria e persiste o registro. Toda a lógica de
    deduplicação, cooldown e locks deve ser executada ANTES de chamar
    esta função, pela service layer.

    Returns:
        Notificação criada. Lança exceção em caso de erro.
    """
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
        dedup_hash=dedup_hash,
        payload=payload,
        priority=priority,
        cooldown_seconds=cooldown_seconds,
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

def get_pending_notifications(
    db: Session,
    *,
    limit: int = 100,
    now: datetime | None = None,
    notification_ids: list[UUID] | None = None,
) -> list[Notification]:
    """ Recupera notificações pendentes com elegibilidade de retry """
    reference = _normalize_datetime(now)
    query = db.query(Notification).filter(
        Notification.status.in_([NotificationStatus.pending, NotificationStatus.failed]),
        Notification.attempts < Notification.max_attempts,
    )
    if notification_ids:
        query = query.filter(Notification.id.in_(notification_ids))
    query = query.filter(
        or_(
            and_(
                Notification.next_attempt_at.is_(None),
                Notification.created_at <= reference,
            ),
            Notification.next_attempt_at <= reference,
        )
    )
    return query.order_by(Notification.created_at.asc()).limit(limit).all()

def acquire_notification_for_processing(
        db: Session,
        *,
        notification_id: UUID,
) -> Notification | None:
    """ Reserva uma notificação para processamento garantindo exclusão mútua """
    notification = (
        db.query(Notification)
        .filter(Notification.id == notification_id)
        .with_for_update(skip_locked=True)
        .first()
    )
    if notification is None:
        return None
    if notification.status not in {NotificationStatus.pending, NotificationStatus.failed}:
        return None
    if notification.attempts >= notification.max_attempts:
        return None

    now = datetime.now(timezone.utc)
    notification.status = NotificationStatus.processing
    notification.attempts += 1
    notification.last_attempt_at = now
    notification.next_attempt_at = None
    db.flush()
    return notification

def mark_notification_sent(
    db: Session,
    *,
    notification: Notification,
    commit: bool = False,
) -> Notification:
    """ Marca a notificação como enviada no banco de dados.

    O registro de cooldown no Redis deve ser feito pela service layer
    após chamar esta função, usando notification_redis_repository.set_cooldown_marker().
    """
    sent_at = datetime.now(timezone.utc)
    notification.status = NotificationStatus.sent
    notification.sent_at = sent_at
    notification.cooldown_expires_at = (
        sent_at + timedelta(seconds=notification.cooldown_seconds)
        if notification.cooldown_seconds > 0
        else None
    )
    if commit:
        db.commit()
        db.refresh(notification)
    else:
        db.flush()
    return notification

def mark_notification_failed(
    db: Session,
    *,
    notification: Notification,
    next_attempt_at: datetime | None = None,
    commit: bool = False,
) -> Notification:
    """ Marca a notificação como falha para permitir nova tentativa """
    notification.status = NotificationStatus.failed
    notification.next_attempt_at = _normalize_datetime(next_attempt_at) if next_attempt_at else None
    if commit:
        db.commit()
        db.refresh(notification)
    else:
        db.flush()
    return notification

def mark_notification_dead_letter(
    db: Session,
    *,
    notification: Notification,
    commit: bool = False,
) -> Notification:
    """ Marca a notificação como falha permanente para inspeção """
    notification.status = NotificationStatus.dead_letter
    notification.dead_lettered_at = datetime.now(timezone.utc)
    if commit:
        db.commit()
        db.refresh(notification)
    else:
        db.flush()
    return notification

def add_notification_attempt(
    db: Session,
    *,
    notification_id: UUID,
    attempt_number: int,
    status: DeliveryStatus,
    provider_message_id: str | None = None,
    provider_response: dict[str, Any] | None = None,
    error_code: str | None = None,
    error_message: str | None = None,
    latency_ms: int | None = None,
    attempted_at: datetime | None = None,
    commit: bool = False,
) -> NotificationAttempt:
    """ Registra uma tentativa de entrega para auditoria """
    record = NotificationAttempt(
        notification_id=notification_id,
        attempt_number=attempt_number,
        status=status,
        provider_message_id=provider_message_id,
        provider_response=provider_response,
        error_code=error_code,
        error_message=error_message,
        latency_ms=latency_ms,
        attempted_at=_normalize_datetime(attempted_at) if attempted_at else None,
    )
    db.add(record)
    if commit:
        db.commit()
        db.refresh(record)
    else:
        db.flush()

    logger.info(
        "notification_attempt_created",
        notification_attempt_id=str(record.id),
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

def list_alert_rules(
    db: Session,
    *,
    user_id: UUID,
    monitored_product_id: UUID | None = None,
    alert_type: AlertType | None = None,
) -> list[AlertRule]:
    """ Lista regras de alerta ativas por usuário e contexto opcional """
    query = db.query(AlertRule).filter(
        AlertRule.user_id == user_id,
        AlertRule.enabled.is_(True),
    )
    if monitored_product_id is not None:
        query = query.filter(AlertRule.monitored_product_id == monitored_product_id)
    if alert_type is not None:
        query = query.filter(AlertRule.alert_type == alert_type)
    return query.order_by(AlertRule.created_at.desc()).all()

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

def get_last_sent_at(
    db: Session,
    *,
    monitored_product_id: UUID | None,
    channel: NotificationChannel,
) -> datetime | None:
    """ Recupera o último envio registrado por produto e canal """
    query = db.query(Notification.sent_at).filter(
        Notification.channel == channel,
        Notification.status == NotificationStatus.sent,
    )
    if monitored_product_id is None:
        query = query.filter(Notification.monitored_product_id.is_(None))
    else:
        query = query.filter(Notification.monitored_product_id == monitored_product_id)
    return query.order_by(Notification.sent_at.desc()).scalar()

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

def get_notification_settings(
    db: Session,
    *,
    user_id: UUID,
) -> dict[NotificationChannel, bool]:
    """ Obtém o resumo de habilitação por canal para o usuário """
    preferences = list_user_notification_preferences(db, user_id=user_id, monitored_product_id=None)
    channel_settings = {channel: DEFAULT_CHANNEL_SETTINGS.get(channel, False) for channel in DEFAULT_CHANNEL_SETTINGS}

    for channel in channel_settings:
        channel_prefs = [pref for pref in preferences if pref.channel == channel]
        if not channel_prefs:
            continue
        enabled_values = {pref.enabled for pref in channel_prefs}
        if len(enabled_values) > 1:
            logger.warning(
                "notification_settings_inconsistent",
                user_id=str(user_id),
                channel=channel.value,
                enabled=list(enabled_values),
            )
        channel_settings[channel] = any(enabled_values)

    logger.info(
        "notification_settings_loaded",
        user_id=str(user_id),
        settings={channel.value: enabled for channel, enabled in channel_settings.items()},
    )
    return channel_settings

def update_notification_settings(
    db: Session,
    *,
    user_id: UUID,
    settings: dict[NotificationChannel, bool],
) -> dict[NotificationChannel, bool]:
    """ Atualiza as preferências globais de notificação por canal """
    for channel, enabled in settings.items():
        for alert_type in AlertType:
            upsert_user_notification_preference(
                db,
                user_id=user_id,
                monitored_product_id=None,
                alert_type=alert_type,
                channel=channel,
                enabled=enabled,
                channel_metadata={"source": "settings"},
                commit=False,
            )

    db.commit()
    logger.info(
        "notification_settings_updated",
        user_id=str(user_id),
        settings={channel.value: enabled for channel, enabled in settings.items()},
    )
    return settings
