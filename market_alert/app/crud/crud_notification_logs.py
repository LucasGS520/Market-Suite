""" Operações CRUD para "logs" de notificações """

from datetime import datetime, timezone, timedelta
from typing import List
from uuid import UUID

from sqlalchemy.orm import Session

from app.models.models_alerts import NotificationLog
from app.enums.enums_alerts import ChannelType, AlertType


def create_notification_log(db: Session, user_id: UUID, channel: ChannelType, subject: str, message: str, alert_rule_id: UUID | None = None,
                            alert_type: AlertType | None = None, provider_metadata: dict | None = None, success: bool = True, error: str | None = None) -> NotificationLog:
    """ Cria um registro de "log" de notificação no banco de dados """
    log = NotificationLog(
        user_id=user_id,
        alert_rule_id=alert_rule_id,
        alert_type=alert_type,
        channel=channel,
        subject=subject,
        message=message,
        provider_metadata=provider_metadata,
        success=success,
        error=error
    )
    db.add(log)
    db.commit()
    db.refresh(log)
    return log

def get_notification_logs(db: Session, user_id: UUID, limit: int = 20, offset: int = 0, start: datetime | None = None, end: datetime | None = None,
                          channel: ChannelType | None = None, success: bool | None = None, alert_rule_id: UUID | None = None, cursor: datetime | None = None) -> List[NotificationLog]:
    """ Obtém os "logs" de notificação de um usuário aplicando filtros opcionais """
    query = db.query(NotificationLog).filter(NotificationLog.user_id == user_id)

    if start:
        query = query.filter(NotificationLog.sent_at >= start)
    if end:
        query = query.filter(NotificationLog.sent_at <= end)
    if channel:
        query = query.filter(NotificationLog.channel == channel)
    if success is not None:
        query = query.filter(NotificationLog.success == success)
    if alert_rule_id:
        query = query.filter(NotificationLog.alert_rule_id == alert_rule_id)
    if cursor:
        query = query.filter(NotificationLog.sent_at < cursor)

    return query.order_by(NotificationLog.sent_at.desc()).offset(offset).limit(limit).all()

def has_recent_duplicate_notification(db: Session, user_id: UUID, subject: str, message: str, window_seconds: int) -> bool:
    """ Verifica se uma notificação idêntica foi enviada recentemente """
    cutoff = datetime.now(timezone.utc) - timedelta(seconds=window_seconds)
    return (
        db.query(NotificationLog)
        .filter(
            NotificationLog.user_id == user_id,
            NotificationLog.subject == subject,
            NotificationLog.message == message,
            NotificationLog.success == True,
            NotificationLog.sent_at >= cutoff
        )
        .first()
        is not None
    )
