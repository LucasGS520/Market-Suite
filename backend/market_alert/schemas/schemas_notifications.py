""" Esquemas Pydantic para eventos, alertas e notificações """

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from market_alert.enums.enums_notifications import AlertType, DeliveryStatus, EventType, NotificationChannel, NotificationStatus


class EventLogCreate(BaseModel):
    """ Payload mínimo para persistir um evento de domínio """
    event_type: EventType = Field(..., description="Tipo do evento processado")
    trace_id: str = Field(..., description="Identificador de rastreamento obrigatório")
    payload: dict[str, Any] = Field(..., description="Origem do evento dentro do ecossistema")
    source: str | None = Field(None, description="Origem do evento dentro do ecossistema")
    monitored_product_id: UUID | None = Field(None, description="Monitorado associado ao evento")
    user_id: UUID | None = Field(None, description="Usuário relacionado ao evento")
    ocurred_at: datetime | None = Field(None, description="Momento real do evento, se disponível")

class EventLogResponse(BaseModel):
    """ Representação serializada de um evento persistido """
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    event_type: EventType
    trace_id: str
    payload: dict[str, Any]
    source: str | None = None
    monitored_product_id: UUID | None = None
    user_id: UUID | None = None
    ocurred_at: datetime
    created_at: datetime

class AlertRuleCreate(BaseModel):
    """ Payload para configurar uma regra de alerta """
    user_id: UUID = Field(..., description="Usuário responsável pela regra")
    monitored_product_id: UUID | None = Field(None, description="Monitorado específico quando aplicável")
    alert_type: AlertType = Field(..., description="Tipo de alerta a ser avaliado")
    channel: NotificationChannel = Field(..., description="Canal preferencial para entrega")
    threshold_value: float | None = Field(None, description="valor alvo para disparo")
    threshold_percent: float | None = Field(None, description="Percentual alvo para disparo")
    cooldown_seconds: int = Field(0, description="Cooldown em segundos entre alertas")
    enabled: bool = Field(True, description="Indica se regra está ativa")
    rule_config: dict[str, Any] | None = Field(None, description="Configurações adicionais específicas da regra")

class AlertRuleResponse(BaseModel):
    """ Representação serializada de uma regra de alerta """
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    user_id: UUID
    monitored_product_id: UUID | None = None
    alert_type: AlertType
    channel: NotificationChannel
    threshold_value: float | None = None
    threshold_percent: float | None = None
    cooldown_seconds: int
    enabled: bool
    rule_config: dict[str, Any] | None = None
    last_triggered_at: datetime | None = None
    created_at: datetime
    updated_at: datetime

class NotificationCreate(BaseModel):
    """ Payload para persistir uma notificação pendente """
    event_id: UUID = Field(..., description="Evento de domínio que originou a notificação")
    alert_id: UUID | None = Field(None, description="Regra de alerta responsável")
    user_id: UUID = Field(..., description="Usuário associado à notificação")
    monitored_product_id: UUID | None = Field(None, description="Monitorado associado à notificação")
    channel: NotificationChannel = Field(..., description="Canal de entrega")
    recipient: str = Field(..., description="Destino do canal")
    subject: str | None = Field(None, description="Assunto da mensagem")
    message: str | None = Field(None, description="Conteúdo da notificação")
    dedup_hash: str = Field(..., description="Hash de deduplicação para evitar duplicidade")
    payload: dict[str, Any] | None = Field(None, description="Payload estruturado para o canal")
    priority: int = Field(0, description="Prioridade relativa da notificação")
    cooldown_seconds: int = Field(0, description="Cooldown configurado em segundos")
    status: NotificationStatus = Field(NotificationStatus.pending, description="Status inicial da notificação")
    max_attempts: int = Field(3, description="Quantidade máxima de tentativas de entrega")
    next_attempt_at: datetime | None = Field(None, description="Momento sugerido para nova tentativa de entrega")

class NotificationRead(BaseModel):
    """ Representação serializada da notificação persistida """
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    event_id: UUID
    alert_id: UUID | None = None
    user_id: UUID
    monitored_product_id: UUID | None = None
    channel: NotificationChannel
    recipient: str
    subject: str | None = None
    message: str | None = None
    dedup_hash: str
    payload: dict[str, Any] | None = None
    priority: int
    cooldown_seconds: int
    status: NotificationStatus
    attempts: int
    max_attempts: int
    next_attempt_at: datetime | None = None
    last_attempt_at: datetime | None = None
    sent_at: datetime | None = None
    cooldown_expires_at: datetime | None = None
    dead_lettered_at: datetime | None = None
    created_at: datetime
    updated_at: datetime

class NotificationAttemptCreate(BaseModel):
    """ Payload para registrar tentativa de entrega """
    notification_id: UUID = Field(..., description="Identificador da notificação")
    attempt_number: int = Field(..., description="Número sequencial da tentativa")
    status: DeliveryStatus = Field(..., description="Resultado da tentativa")
    provider_message_id: str | None = Field(None, description="Identificador do provedor")
    provider_response: dict[str, Any] | None = Field(None, description="Resposta do provedor")
    error_code: str | None = Field(None, description="Código de erro do provedor")
    error_message: str | None = Field(None, description="Mensagem de erro quando houver")
    latency_ms: int | None = Field(None, description="Latência observada na entrega")
    attempted_at: datetime | None = Field(None, description="Momento da tentativa de entrega")

class NotificationAttemptRead(BaseModel):
    """ Representação serializada do registro de entrega """
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    notification_id: UUID
    attempt_number: int
    status: DeliveryStatus
    provider_message_id: str | None = None
    provider_response: dict[str, Any] | None = None
    error_code: str | None = None
    error_message: str | None = None
    latency_ms: int | None = None
    attempted_at: datetime | None = None
    created_at: datetime

class UserNotificationPreferenceCreate(BaseModel):
    """ Payload para criar preferências de notificação """
    user_id: UUID = Field(..., description="Usuário associado")
    monitored_product_id: UUID | None = Field(None, description="Monitorado específico, quando aplicável")
    alert_type: AlertType = Field(..., description="Tipo de alerta configurado")
    channel: NotificationChannel = Field(..., description="Canal preferencial")
    destination: str | None = Field(None, description="Destino específico para o canal")
    enabled: bool = Field(True, description="Indica se o canal está habilitado")
    cooldown_seconds: int = Field(0, description="Cooldown por monitorado e tipo")
    channel_metadata: dict[str, Any] | None = Field(None, description="Configurações adiconais do canal")

class UserNotificationPreferenceUpdate(BaseModel):
    """ Representação serializada de uma preferência """
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    user_id: UUID
    monitored_product_id: UUID | None = None
    alert_type: AlertType
    channel: NotificationChannel
    destination: str | None = None
    enabled: bool
    cooldown_seconds: int
    channel_metadata: dict[str, Any] | None = None
    last_notified_at: datetime | None = None
    created_at: datetime
    updated_at: datetime

class UserNotificationPreferenceResponse(UserNotificationPreferenceUpdate):
    """ Representação de preferência usada em listagens """
    pass

class NotificationPaginationMeta(BaseModel):
    """ Metadados de paginação para listagens de notificações """
    total: int = Field(..., description="Quantidade total de registros disponíveis")
    page: int = Field(..., description="Página atual baseada em 1")
    per_page: int = Field(..., description="Quatidade de registros por página")

class PaginatedNotificationResponse(BaseModel):
    """ Envelope paginado com notificações """
    items: list[NotificationRead]
    meta: NotificationPaginationMeta
    