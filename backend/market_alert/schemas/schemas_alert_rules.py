""" Esquemas de regras de alerta e registro de notificações """

from typing import Optional, ClassVar

from uuid import UUID
from datetime import datetime
from pydantic import BaseModel, ConfigDict, Field, model_validator

from market_alert.enums.enums_alerts import (
    AlertType,
    ChannelType,
    AlertSeverity,
    NotificationStatus,
)
from market_alert.enums.enums_products import ProductStatus


class AlertRuleCreate(BaseModel):
    """ Esquema de criação para regras de alerta enxutas

    O contrato aceita apenas os tipos necessários para o fluxo
    simplificado: mudança de preço e variações de disponibilidade.
    Limiares numéricos foram removidos para reduzir heurísticas
    dinâmicas e tornar o comportamento previsível.
    """
    allowed_rule_types: ClassVar[set[AlertType]] = {
        AlertType.PRICE_CHANGE,
        AlertType.PRICE_TARGET,
        AlertType.LISTING_PAUSED,
        AlertType.LISTING_REMOVED,
        AlertType.SCRAPING_ERROR,
    }

    user_id: UUID
    monitored_product_id: Optional[UUID] = None
    rule_type: AlertType
    product_status: Optional[ProductStatus] = None
    enabled: bool = True
    
    @model_validator(mode="after")
    def validate_rule_type(cls, values: "AlertRuleCreate") -> "AlertRuleCreate":
        """Permite apenas tipos de alerta essenciais

        Mantemos ``PRICE_TARGET`` como apelido para ``PRICE_CHANGE``
        por retrocompatibilidade, porém sem aceitar thresholds.
        """
        if values.rule_type not in cls.allowed_rule_types:
            raise ValueError(
                "Tipo de alerta não suportado nesta versão simplificada"
            )
        return values

class QuickAlertRuleCreate(BaseModel):
    """ Esquema simplificado para criação rápida de regra """
    monitored_product_id: Optional[UUID] = None
    rule_type: AlertType = AlertType.PRICE_CHANGE
    product_status: Optional[ProductStatus] = None
    
    @model_validator(mode="after")
    def validate_rule_type(cls, values: "QuickAlertRuleCreate") -> "QuickAlertRuleCreate":
        """Garante que apenas regras suportadas sejam criadas rapidamente"""
        if values.rule_type not in AlertRuleCreate.allowed_rule_types:
            raise ValueError(
                "Tipo de alerta não suportado para criação rápida"
            )
        return values

class AlertRuleUpdate(BaseModel):
    """ Esquema de atualização de regras de alerta """
    user_id: Optional[UUID] = None
    monitored_product_id: Optional[UUID] = None
    rule_type: Optional[AlertType] = None
    product_status: Optional[ProductStatus] = None
    enabled: Optional[bool] = None

class AlertRuleResponse(BaseModel):
    """ Esquema de resposta para regras de alerta """
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    user_id: UUID
    monitored_product_id: Optional[UUID] = None
    rule_type: AlertType
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
    comparison_id: Optional[UUID] = None
    severity: Optional[AlertSeverity] = None
    status: NotificationStatus
    channel: ChannelType
    subject: str
    message: str
    provider_metadata: Optional[dict] = None
    sent_at: datetime
    success: bool = True
    error: Optional[str] = None
