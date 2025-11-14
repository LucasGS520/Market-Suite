""" Gerenciador de envio de alertas

Recebe uma lista de canais e repassa as
notificações a cada um deles.
"""

from __future__ import annotations

from typing import Iterable, List, TYPE_CHECKING, Any
from uuid import UUID

if TYPE_CHECKING:
    from market_alert.models.models_alerts import AlertRule

import asyncio
import hashlib
import json
import time
from decimal import Decimal, InvalidOperation

import structlog
from sqlalchemy.orm import Session

from market_alert.crud.crud_alert_rules import get_active_alert_rules_for_product as crud_get_active_rules
from market_alert.crud.crud_notification_logs import create_notification_log

from .channels import NotificationChannel
from .channels.email import EmailChannel
from .channels.sms import SMSChannel
from .channels.push import PushChannel
from .channels.whatsapp import WhatsAppChannel
from .channels.slack import SlackChannel

from market_alert.enums.enums_alerts import (
    ChannelType,
    AlertType,
    AlertSeverity,
    NotificationStatus,
)
from market_alert.core.config_alert import settings
from shared import metrics
from shared.utils.redis_client import set_key_with_ttl
from shared.infra.redis_pubsub import publish_message


logger = structlog.get_logger("alerts")

#Evita repeticão infinita de avisos sobre configurações faltantes
WARNING_COOLDOWN_SECONDS = 300.0
_LOGGED_MISSING_CHANNELS: dict[str, tuple[frozenset[str], float, int]] = {}

COOLDOWN_KEY_TEMPLATE = "alerts:cooldown:{monitored_id}:{alert_type}"
HASH_KEY_TEMPLATE = "alerts:hash:{monitored_id}:{payload_hash}"

def __verify_channel_settings() -> dict[str, list[str]]:
    """ Verifica variáveis obrigatórias para todos os canais de notificação """
    #Retorna um dicionário com variáveis ausentes por canal para evitar falhas silenciosas
    missing: dict[str, list[str]] = {}

    if not settings.SMTP_HOST:
        missing["email"] = ["SMTP_HOST"]

    sms_required = ["TWILIO_ACCOUNT_SID", "TWILIO_AUTH_TOKEN", "TWILIO_SMS_FROM"]
    sms_missing = [var for var in sms_required if not getattr(settings, var)]
    if sms_missing:
        missing["sms"] = sms_missing

    wa_required = ["TWILIO_ACCOUNT_SID", "TWILIO_AUTH_TOKEN", "TWILIO_WHATSAPP_FROM"]
    wa_missing = [var for var in wa_required if not getattr(settings, var)]
    if wa_missing:
        missing["whatsapp"] = wa_missing

    if not settings.FCM_SERVER_KEY:
        missing["push"] = ["FCM_SERVER_KEY"]

    if not settings.SLACK_WEBHOOK_URL:
        missing["slack"] = ["SLACK_WEBHOOK_URL"]

    for channel, vars_missing in missing.items():
        missing_set = frozenset(vars_missing)
        state = _LOGGED_MISSING_CHANNELS.get(channel)
        should_log = True

        if state:
            previous_missing, last_logged_at, last_logger_id = state
            same_missing = previous_missing == missing_set
            within_cooldown = (time.monotonic() - last_logged_at) < WARNING_COOLDOWN_SECONDS
            same_logger = last_logger_id == id(logger)
            if same_missing and within_cooldown and same_logger:
                should_log = False

        if should_log:
            now = time.monotonic()
            logger.warning("channel_vars_missing", channel=channel, missing=vars_missing)
            _LOGGED_MISSING_CHANNELS[channel] = (missing_set, now, id(logger))
        else:
            _LOGGED_MISSING_CHANNELS[channel] = state

        metrics.NOTIFICATIONS_SKIPPED_TOTAL.labels(reason="missing_settings").inc()

    return missing

def get_active_alert_rules_for_product(db: Session, user_id: UUID, monitored_product_id: UUID | None):
    """ Compatibilidade com importações antigas """
    return crud_get_active_rules(db, user_id, monitored_product_id)

class NotificationManager:
    """ Orquestra o envio de alertas para múltiplos canais aplicando regras de supressão """
    def __init__(
        self,
        channels: Iterable[NotificationChannel] | None = None,
        *,
        cooldown_seconds: int | None = None,
        dedupe_ttl_seconds: int | None = None,
        price_tolerance: Decimal | None = None,
    ) -> None:
        self.channels: List[NotificationChannel] = list(channels or [])
        self.cooldown_seconds = (
            cooldown_seconds
            if cooldown_seconds is not None
            else int(getattr(settings, "ALERT_COOLDOWN_SECONDS", 0))
        )
        self.dedupe_ttl_seconds = (
            dedupe_ttl_seconds
            if dedupe_ttl_seconds is not None
            else int(getattr(settings, "ALERT_DEDUPE_TTL_SECONDS", 0))
        )
        tolerance_source = price_tolerance if price_tolerance is not None else settings.PRICE_TOLERANCE
        self.price_tolerance = Decimal(str(tolerance_source))

    def _resolve_channel_type(self, channel: NotificationChannel) -> ChannelType:
        """ Determina o tipo de canal associado à instância recebida """
        if isinstance(channel, SlackChannel):
            return ChannelType.SLACK
        
        name = channel.__class__.__name__.replace("Channel", "").lower()
        try:
            return ChannelType(name)
        except ValueError:
            # Canais personalizados tratados como webhook genérico
            return ChannelType.WEBHOOK

    async def _send_one_async(
        self,
        db: Session,
        user,
        subject: str,
        message: str,
        alert_rule_id: str | None,
        channel: NotificationChannel,
        alert_type: AlertType | None,
        *,
        comparison_id: UUID | None = None,
        severity: AlertSeverity | None = None,
    ) -> None:
        """ Envia uma notificação para um único canal de forma assíncrona """
        channel_type = self._resolve_channel_type(channel)

        success = True
        error: str | None = None
        metadata: dict | None = None
        start = time.time()
        try:
            #Dispara o envio, falhas não interrompem os demais canais
            metadata = await channel.send_async(user, subject, message)
        except Exception as exc:
            success = False
            error = str(exc)
            logger.error("notification_failed", channel=channel_type.value, error=error)
        finally:
            duration = time.time() - start
            metrics.NOTIFICATION_SEND_DURATION_SECONDS.labels(channel=channel_type.value).observe(duration)
            metrics.NOTIFICATIONS_SENT_TOTAL.labels(channel=channel_type.value, success=str(success)).inc()

        log = create_notification_log(
            db,
            user_id=user.id,
            channel=channel_type,
            subject=subject,
            message=message,
            alert_rule_id=alert_rule_id,
            alert_type=alert_type,
            provider_metadata=metadata,
            success=success,
            error=error,
            comparison_id=comparison_id,
            severity=severity,
            status=NotificationStatus.SENT if success else NotificationStatus.FAILED,
        )
        _publish_notification_event(
            log,
            channel_type=channel_type,
            user_id=str(user.id),
            alert_type=alert_type,
            severity=severity,
            comparison_id=comparison_id,
            success=success,
        )

    async def send_async(
        self,
        db: Session,
        user,
        subject: str,
        message: str,
        alert_rule_id=None,
        alert_type: AlertType | None = None,
        *,
        comparison_id: UUID | None = None,
        severity: AlertSeverity | None = None,
    ) -> None:
        """ Envia a notificação usando todos os canais de forma assíncrona """
        tasks = [
            self._send_one_async(
                db,
                user,
                subject,
                message,
                alert_rule_id,
                channel,
                alert_type,
                comparison_id=comparison_id,
                severity=severity,
            )
            for channel in self.channels
        ]
        #gather executa todos os envios em paralelo
        await asyncio.gather(*tasks)

    def send(
        self,
        db: Session,
        user,
        subject: str,
        message: str,
        alert_rule_id=None,
        alert_type: AlertType | None = None,
        *,
        comparison_id: UUID | None = None,
        severity: AlertSeverity | None = None,
    ) -> None:
        """ Envia a notificação, lidando com contexto síncrono ou assíncrono """
        coro = self.send_async(
            db,
            user,
            subject,
            message,
            alert_rule_id=alert_rule_id,
            alert_type=alert_type,
            comparison_id=comparison_id,
            severity=severity,
        )

        try:
            asyncio.get_running_loop()
        except RuntimeError:
            #Sem loop running -> executa de forma síncrona
            asyncio.run(coro)
        else:
            #Dentro de um loop -> retorna a coroutine para ser aguardada
            return coro

    def _extract_decimal(self, alert: dict | None, key: str) -> Decimal | None:
        """ Extrai valores numéricos do alerta de forma tolerante a tipos """

        if not alert or key not in alert:
            return None

        value: Any = alert.get(key)
        if value is None:
            return None

        try:
            return Decimal(str(value)).copy_abs()
        except (InvalidOperation, TypeError, ValueError):
            return None

    def _is_within_price_tolerance(self, alert: dict | None) -> bool:
        """ Avalia se a variação do alerta é inferior à tolerância configurada """

        if not alert:
            return False

        deltas = [
            self._extract_decimal(alert, "delta_x_monitored"),
            self._extract_decimal(alert, "change"),
        ]

        for delta in deltas:
            if delta is None:
                continue
            if delta < self.price_tolerance:
                return True
        return False

    def _infer_severity(self, alert: dict | None, alert_type: AlertType | None) -> AlertSeverity:
        """ Define automaticamente a severidade do alerta """

        if alert_type in {AlertType.LISTING_REMOVED, AlertType.LISTING_PAUSED, AlertType.SCRAPING_ERROR}:
            return AlertSeverity.HIGH

        if alert_type == AlertType.PRICE_CHANGE:
            change = self._extract_decimal(alert, "change")
            if change is not None:
                if change >= self.price_tolerance * Decimal("5"):
                    return AlertSeverity.HIGH
                if change >= self.price_tolerance * Decimal("2"):
                    return AlertSeverity.MEDIUM
                return AlertSeverity.LOW

        return AlertSeverity.MEDIUM

    def _build_payload_hash(
        self,
        subject: str,
        message: str,
        alert_type: AlertType | None,
        alert: dict | None,
        comparison_id: UUID | None,
    ) -> str:
        """ Calcula um hash estável do conteúdo relevante da notificação """

        base_payload = {
            "subject": subject,
            "message": message,
            "alert_type": alert_type.value if alert_type else None,
            "comparison_id": str(comparison_id) if comparison_id else None,
            "alert": alert or {},
        }
        serialized = json.dumps(base_payload, sort_keys=True, default=str)
        return hashlib.md5(serialized.encode("utf-8")).hexdigest()

    def _should_skip_due_to_cooldown(self, monitored_id: str | None, alert_type: AlertType | None) -> bool:
        """ Controla o cooldown por produto monitorado e tipo de alerta """

        if monitored_id is None or self.cooldown_seconds <= 0:
            return False

        key = COOLDOWN_KEY_TEMPLATE.format(
            monitored_id=monitored_id,
            alert_type=alert_type.value if alert_type else "generic",
        )
        result = set_key_with_ttl(key, "1", self.cooldown_seconds, only_if_absent=True)
        return result is False

    def _should_skip_due_to_duplicate(self, monitored_id: str | None, payload_hash: str | None) -> bool:
        """ Evita reenvio de notificações idênticas recentemente disparadas """

        if monitored_id is None or not payload_hash or self.dedupe_ttl_seconds <= 0:
            return False

        key = HASH_KEY_TEMPLATE.format(monitored_id=monitored_id, payload_hash=payload_hash)
        result = set_key_with_ttl(key, "1", self.dedupe_ttl_seconds, only_if_absent=True)
        return result is False

    def _status_from_reason(self, reason: str) -> NotificationStatus:
        """ Mapeia a razão de supressão para o status do log """

        mapping = {
            "cooldown": NotificationStatus.SKIPPED_COOLDOWN,
            "duplicate": NotificationStatus.SKIPPED_DUPLICATE,
            "tolerance": NotificationStatus.SKIPPED_TOLERANCE,
        }
        return mapping.get(reason, NotificationStatus.SKIPPED_COOLDOWN)

    def send_rendered(
        self,
        db: Session,
        user,
        subject: str,
        renderer,
        monitored,
        alert: dict,
        alert_rule_id: str | None = None,
        alert_type: AlertType | None = None,
    ) -> None:
        """ Renderiza a mensagem para cada canal e envia a notificação """

        monitored_id = getattr(monitored, "id", None)
        comparison_id = None
        if isinstance(alert, dict):
            raw_comparison = alert.get("comparison_id")
            if raw_comparison is not None:
                try:
                    comparison_id = raw_comparison if isinstance(raw_comparison, UUID) else UUID(str(raw_comparison))
                except (ValueError, TypeError):
                    comparison_id = None

        plain_message = renderer(monitored, alert, html=False)
        severity = self._infer_severity(alert, alert_type)

        skip_reason: str | None = None
        if self._is_within_price_tolerance(alert):
            skip_reason = "tolerance"

        payload_hash: str | None = None
        if skip_reason is None:
            if self._should_skip_due_to_cooldown(str(monitored_id) if monitored_id else None, alert_type):
                skip_reason = "cooldown"

        if skip_reason is None:
            payload_hash = self._build_payload_hash(subject, plain_message, alert_type, alert, comparison_id)
            if self._should_skip_due_to_duplicate(str(monitored_id) if monitored_id else None, payload_hash):
                skip_reason = "duplicate"

        if skip_reason:
            metrics.NOTIFICATIONS_SKIPPED_TOTAL.labels(reason=skip_reason).inc()
            logger.info(
                "notification_suppressed",
                reason=skip_reason,
                monitored_id=str(monitored_id) if monitored_id else None,
                alert_type=alert_type.value if alert_type else None,
            )
            status = self._status_from_reason(skip_reason)
            for channel in self.channels:
                channel_type = self._resolve_channel_type(channel)
                create_notification_log(
                    db,
                    user_id=user.id,
                    channel=channel_type,
                    subject=subject,
                    message=plain_message,
                    alert_rule_id=alert_rule_id,
                    alert_type=alert_type,
                    provider_metadata=None,
                    success=False,
                    error=skip_reason,
                    comparison_id=comparison_id,
                    severity=severity,
                    status=status,
                )
            return
        
        async def _dispatch():
            tasks = []
            for channel in self.channels:
                html = isinstance(channel, EmailChannel)
                #Renderiza texto puro em HTML conforme o canal
                message = renderer(monitored, alert, html=html)
                tasks.append(
                    self._send_one_async(
                        db,
                        user,
                        subject,
                        message,
                        alert_rule_id,
                        channel,
                        alert_type,
                        comparison_id=comparison_id,
                        severity=severity,
                    )
                )
            await asyncio.gather(*tasks)

        asyncio.run(_dispatch())

def get_notification_manager() -> NotificationManager:
    """ Cria uma instância de ´NotificationManager´ com os canais padrão """
    #As configurações dos canais são verificadas sempre que o gerenciador é obtido para evitar dependência da ordem dos testes
    __verify_channel_settings()
    #Conjunto mínimo de canais habilitados
    channels = [
        EmailChannel(),
        SMSChannel(),
        PushChannel(),
        WhatsAppChannel()
    ]
    if settings.SLACK_WEBHOOK_URL:
        channels.append(SlackChannel())
    return NotificationManager(channels)

def _publish_notification_event(
    log,
    *,
    channel_type: ChannelType,
    user_id: str,
    alert_type: AlertType | None,
    severity: AlertSeverity | None,
    comparison_id: UUID | None,
    success: bool,
) -> None:
    """Envia para o Redis o evento de alerta criado para consumo em tempo real."""

    notification_id = getattr(log, "id", None)
    sent_at = getattr(log, "sent_at", None)
    status = getattr(log, "status", None)

    event_payload = {
        "type": "alert.created",
        "notification_id": str(notification_id) if notification_id else None,
        "user_id": user_id,
        "alert_rule_id": str(getattr(log, "alert_rule_id", None)) if getattr(log, "alert_rule_id", None) else None,
        "comparison_id": str(comparison_id or getattr(log, "comparison_id", None))
        if (comparison_id or getattr(log, "comparison_id", None))
        else None,
        "channel": channel_type.value,
        "status": status.value if status else None,
        "success": bool(success),
        "created_at": sent_at.isoformat() if sent_at else None,
        "subject": getattr(log, "subject", None),
        "message": getattr(log, "message", None),
        "severity": (severity.value if severity else None)
        or (getattr(log, "severity", None).value if getattr(log, "severity", None) else None),
        "alert_type": (alert_type.value if alert_type else None)
        or (getattr(log, "alert_type", None).value if getattr(log, "alert_type", None) else None),
        "channels": [f"user:{user_id}"],
    }

    if not publish_message("notifications", event_payload):
        logger.warning(
            "notification_event_publish_failed",
            notification_id=str(notification_id) if notification_id else None,
        )
        