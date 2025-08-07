""" Esquemas de regras de alerta e registro de notificações """

from decimal import Decimal
from typing import Optional, Any

from uuid import UUID
from datetime import datetime
from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.enums.enums_alerts import AlertType, ChannelType
from app.enums.enums_products import ProductStatus


class AlertRuleCreate(BaseModel):
    """ Esquema de criação para regras de alerta """
    user_id: UUID
    monitored_product_id: Optional[UUID] = None
    rule_type: AlertType
    threshold_value: Optional[Decimal] = Field(None, gt=0)
    threshold_percent: Optional[float] = Field(None, gt=0, le=100)
    target_price: Optional[Decimal] = Field(None, gt=0)
    product_status: Optional[ProductStatus] = None
    enabled: bool = True

    @field_validator("threshold_percent")
    @classmethod
    def validate_percent(cls, value):
        """ Verifica se o percentual está entre o e 100 """
        if value is not None and not (0 < value <= 100):
            raise ValueError("threshold_percent é necessário estar entre 0 e 100")
        return value

class QuickAlertRuleCreate(BaseModel):
    """ Esquema simplificado para criação rápida de regra """
    monitored_product_id: Optional[UUID] = None
    rule_type: AlertType = AlertType.PRICE_TARGET
    threshold_value: Optional[Decimal] = Field(None, gt=0)
    threshold_percent: Optional[float] = Field(None, gt=0, le=100)
    target_price: Optional[Decimal] = Field(None, gt=0)

    @field_validator("threshold_percent")
    @classmethod
    def validate_percent(cls, value):
        """ Verifica se o percentual está entre 0 e 100 """
        if value is not None and not (0 < value <= 100):
            raise ValueError("threshold_percent é necessário estar entre 0 e 100")
        return value

class AlertRuleUpdate(BaseModel):
    """ Esquema de atualização de regras de alerta """
    user_id: Optional[UUID] = None
    monitored_product_id: Optional[UUID] = None
    rule_type: Optional[AlertType] = None
    threshold_value: Optional[Decimal] = Field(None, gt=0)
    threshold_percent: Optional[float] = Field(None, gt=0, le=100)
    target_price: Optional[Decimal] = Field(None, gt=0)
    product_status: Optional[ProductStatus] = None
    enabled: Optional[bool] = None

    @field_validator("threshold_percent")
    @classmethod
    def validate_percent(cls, value):
        """ Verifica se o percentual está entre 0 e 100 """
        if value is not None and not (0 < value <= 100):
            raise ValueError("threshold_percent é necessário estar entre 0 e 100")
        return value

class AlertRuleResponse(BaseModel):
    """ Esquema de resposta para regras de alerta """
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    user_id: UUID
    monitored_product_id: Optional[UUID] = None
    rule_type: AlertType
    threshold_value: Optional[Decimal] = None
    threshold_percent: Optional[float] = None
    target_price: Optional[Decimal] = None
    product_status: Optional[ProductStatus] = None
    enabled: bool = True
    last_notified_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime

class NotificationLogResponse(BaseModel):
    """ Esquema de resposta para "logs" de notificações """
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    user_id: UUID
    alert_rule_id: Optional[UUID] = None
    alert_type: Optional[AlertType] = None
    channel: ChannelType
    subject: str
    message: str
    provider_metadata: Optional[dict] = None
    sent_at: datetime
    success: bool = True
    error: Optional[str] = None
