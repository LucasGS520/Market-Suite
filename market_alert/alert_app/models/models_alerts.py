""" Modelos de regras de alerta e logs de notificações """

import uuid
from datetime import datetime, timezone

from sqlalchemy import Column, ForeignKey, DateTime, Numeric, Float, Boolean, Text, Enum as PgEnum, JSON
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import relationship

from infra.db import Base
from alert_app.enums.enums_alerts import AlertType, ChannelType
from alert_app.enums.enums_products import ProductStatus


class AlertRule(Base):
    """ Regra de alerta configurada pelo usuário """

    __tablename__ = "alert_rules"

    id = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(PG_UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    monitored_product_id = Column(PG_UUID(as_uuid=True), ForeignKey("monitored_products.id", ondelete="CASCADE"), nullable=True, index=True)

    rule_type = Column(PgEnum(AlertType, name="alert_rule_type_enum"), nullable=False)
    threshold_value = Column(Numeric(10, 2), nullable=True)
    threshold_percent = Column(Float, nullable=True)
    target_price = Column(Numeric(10, 2), nullable=True)
    product_status = Column(PgEnum(ProductStatus, name="product_status_enum"), nullable=True)
    enabled = Column(Boolean, default=True, nullable=False)

    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
    last_notified_at = Column(DateTime(timezone=True), nullable=True)

    user = relationship("User")
    monitored_product = relationship("MonitoredProduct")
    #Lista de notificações enviadas a partir desta regra
    notifications = relationship("NotificationLog", back_populates="alert_rule", cascade="all, delete-orphan")

    def __repr__(self) -> str:
        return (
            f"<AlertRule id={self.id} user_id={self.user_id} rule_type={self.rule_type}>"
        )

class NotificationLog(Base):
    """ Histórico de notificações enviadas aos usuários """

    __tablename__ = "notification_logs"

    id = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(PG_UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    alert_rule_id = Column(PG_UUID(as_uuid=True), ForeignKey("alert_rules.id", ondelete="SET NULL"), nullable=True, index=True)

    alert_type = Column(PgEnum(AlertType, name="notification_alert_type_enum"), nullable=True)
    channel = Column(PgEnum(ChannelType, name="notification_channel_enum"), nullable=False)
    subject = Column(Text, nullable=False)
    message = Column(Text, nullable=False)
    provider_metadata = Column(JSON, nullable=True)
    sent_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    success = Column(Boolean, default=True, nullable=False)
    error = Column(Text, nullable=True)

    user = relationship("User")
    alert_rule = relationship("AlertRule", back_populates="notifications")

    def __repr__(self) -> str:
        status = "ok" if self.success else "error"
        return (
            f"<NotificationLog id={self.id} user_id={self.user_id} status={status}>"
        )
