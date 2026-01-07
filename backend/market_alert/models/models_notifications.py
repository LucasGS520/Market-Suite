""" Modelos SQLAlchemy para eventos, alertas e notificações """

import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    Column,
    DateTime,
    JSON,
    Integer,
    Boolean,
    String,
    Text,
    Float,
    Numeric,
    ForeignKey,
    UniqueConstraint,
    Enum as PgEnum,
)
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import relationship

from shared.infra.db import Base
from market_alert.enums.enums_notifications import (
    EventType,
    AlertType,
    NotificationChannel,
    NotificationStatus,
    DeliveryStatus,
)


class EventLog(Base):
    """ Registro imutável de eventos de domínio """

    __tablename__ = "event_log"

    id = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    event_type = Column(PgEnum(EventType, name="event_type_enum"), nullable=False, index=True)
    trace_id = Column(String(128), nullable=False, index=True)
    payload = Column(JSON, nullable=False)
    source = Column(String(80), nullable=True)
    monitored_product_id = Column(
        PG_UUID(as_uuid=True),
        ForeignKey("monitored_products.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    user_id = Column(
        PG_UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    ocurred_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    created_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))

    notifications = relationship("Notification", back_populates="event_log", cascade="all, delete-orphan")

    def __repr__(self) -> str:
        return f"<EventLog id={self.id} event_type={self.event_type} trace_id={self.trace_id}>"
    
class AlertRule(Base):
    """ Regra configurável para gerar alertas a partir de eventos """

    __tablename__ = "alert_rule"

    __table_args__ = (
        #Garante uma regra única por usuário, monitorado, tipo e canal
        UniqueConstraint("user_id", "monitored_product_id", "alert_type", "channel", name="uq_alert_rule"),
    )

    id = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(
        PG_UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    monitored_product_id = Column(
        PG_UUID(as_uuid=True),
        ForeignKey("monitored_products.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    alert_type = Column(PgEnum(AlertType, name="alert_type_enum"), nullable=False, index=True)
    channel = Column(PgEnum(NotificationChannel, name="notification_channel_enum"), nullable=False)
    threshold_value = Column(Numeric(10, 2), nullable=True)
    threshold_percent = Column(Float, nullable=True)
    cooldown_seconds = Column(Integer, nullable=False, default=0, server_default="0")
    enabled = Column(Boolean, nullable=False, default=True, server_default="true")
    rule_config = Column(JSON, nullable=True)
    last_triggered_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    notifications = relationship("Notification", back_populates="alert_rule")

    def __repr__(self) -> str:
        return f"<AlertRule id={self.id} alert_type={self.alert_type} channel={self.channel}>"
    
class Notification(Base):
    """ Notificação gerada e pronta para entrega por canal """

    __tablename__ = "notifications"

    __table_args__ = (
        #Idempotência por evento, destino e canal
        UniqueConstraint("event_id", "recipient", "channel", name="uq_notification_event_recipient_channel"),
    )

    id = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    event_id = Column(
        PG_UUID(as_uuid=True),
        ForeignKey("event_log.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    alert_id = Column(
        PG_UUID(as_uuid=True),
        ForeignKey("alert_rule.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    user_id = Column(
        PG_UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    monitored_product_id = Column(
        PG_UUID(as_uuid=True),
        ForeignKey("monitored_products.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    channel = Column(PgEnum(NotificationChannel, name="notification_channel_enum"), nullable=False)
    recipient = Column(String(255), nullable=False)
    subject = Column(Text, nullable=True)
    message = Column(Text, nullable=True)
    status = Column(PgEnum(NotificationStatus, name="notification_status_enum"), nullable=False, default=NotificationStatus.pending)
    dedup_hash = Column(String(255), nullable=False, index=True)
    payload = Column(JSON, nullable=True)
    priority = Column(Integer, nullable=False, default=0, server_default="0")
    cooldown_seconds = Column(Integer, nullable=False, default=0, server_default="0")
    attempts = Column(Integer, nullable=False, default=0, server_default="0")
    max_attempts = Column(Integer, nullable=False, default=3, server_default="3")
    next_attempt_at = Column(DateTime(timezone=True), nullable=True)
    last_attempt_at = Column(DateTime(timezone=True), nullable=True)
    sent_at = Column(DateTime(timezone=True), nullable=True)
    cooldown_expires_at = Column(DateTime(timezone=True), nullable=True)
    dead_lettered_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    event_log = relationship("EventLog", back_populates="notifications")
    alert_rule = relationship("AlertRule", back_populates="notifications")
    attempts_records = relationship("NotificationAttempt", back_populates="notification", cascade="all, delete-orphan")

    def __repr__(self) -> str:
        return f"<Notification id={self.id} channel={self.channel} status={self.status}>"
    
class NotificationAttempt(Base):
    """ Registro de tentativa de entrega de notificação """

    __tablename__ = "notification_attempt"

    id = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    notification_id = Column(
        PG_UUID(as_uuid=True),
        ForeignKey("notifications.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    attempt_number = Column(Integer, nullable=False)
    status = Column(PgEnum(DeliveryStatus, name="delivery_status_enum"), nullable=False)
    provider_message_id = Column(String(255), nullable=True)
    provider_response = Column(JSON, nullable=True)
    error_code = Column(String(120), nullable=True)
    error_message = Column(Text, nullable=True)
    latency_ms = Column(Integer, nullable=True)
    attempted_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    created_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))

    notification = relationship("Notification", back_populates="attempts_records")

    def __repr__(self) -> str:
        return f"<NotificationAttempt id={self.id} notification_id={self.notification_id} status={self.status}>"
    
class UserNotificationPreference(Base):
    """ Preferências de notificação do usuário por canal e alerta """

    __tablename__ = "user_notification_preference"

    __table_args__ = (
        #Evita múltiplas preferências para o mesmo contexto
        UniqueConstraint("user_id", "monitored_product_id", "alert_type", "channel", name="uq_user_notification_preference"),
    )

    id = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(
        PG_UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    monitored_product_id = Column(
        PG_UUID(as_uuid=True),
        ForeignKey("monitored_products.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    alert_type = Column(PgEnum(AlertType, name="alert_type_enum"), nullable=False)
    channel = Column(PgEnum(NotificationChannel, name="notification_channel_enum"), nullable=False)
    destination = Column(String(255), nullable=True)
    enabled = Column(Boolean, nullable=False, default=True, server_default="true")
    cooldown_seconds = Column(Integer, nullable=False, default=0, server_default="0")
    channel_metadata = Column(JSON, nullable=True)
    last_notified_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    def __repr__(self) -> str:
        return (
            "<UserNotificationPreference "
            f"id={self.id} user_id={self.user_id} channel={self.channel} alert_type={self.alert_type}>"
        )
    