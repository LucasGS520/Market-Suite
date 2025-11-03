""" Gerenciador de envio de alertas

Recebe uma lista de canais e repassa as
notificações a cada um deles.
"""

from __future__ import annotations

from typing import Iterable, List, TYPE_CHECKING
from uuid import UUID

if TYPE_CHECKING:
    from market_alert.models.models_alerts import AlertRule

import asyncio
import time

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

from market_alert.enums.enums_alerts import ChannelType, AlertType
from market_alert.core.config_alert import settings
from shared import metrics


logger = structlog.get_logger("alerts")

#Evita repeticão infinita de avisos sobre configurações faltantes
WARNING_COOLDOWN_SECONDS = 300.0
_LOGGED_MISSING_CHANNELS: dict[str, tuple[frozenset[str], float, int]] = {}

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
    """ Orquestra o envio de alertas para múltiplos canais """
    def __init__(self, channels: Iterable[NotificationChannel] | None = None) -> None:
        self.channels: List[NotificationChannel] = list(channels or [])

    async def _send_one_async(self, db: Session, user, subject: str, message: str, alert_rule_id: str | None, channel: NotificationChannel, alert_type: AlertType | None) -> None:
        """ Envia uma notificação para um único canal de forma assíncrona """
        if isinstance(channel, SlackChannel):
            channel_type = ChannelType.SLACK
        else:
            name = channel.__class__.__name__.replace("Channel", "").lower()
            try:
                channel_type = ChannelType(name)
            except ValueError:
                #Canais personalizados tratados como webhook genérico
                channel_type = ChannelType.WEBHOOK

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

        create_notification_log(
            db,
            user_id=user.id,
            channel=channel_type,
            subject=subject,
            message=message,
            alert_rule_id=alert_rule_id,
            alert_type=alert_type,
            provider_metadata=metadata,
            success=success,
            error=error
        )

    async def send_async(self, db: Session, user, subject: str, message: str, alert_rule_id=None, alert_type: AlertType | None = None) -> None:
        """ Envia a notificação usando todos os canais de forma assíncrona """
        tasks = [
            self._send_one_async(db, user, subject, message, alert_rule_id, channel, alert_type) for channel in self.channels
        ]
        #gather executa todos os envios em paralelo
        await asyncio.gather(*tasks)

    def send(self, db: Session, user, subject: str, message: str, alert_rule_id=None, alert_type: AlertType | None = None) -> None:
        """ Envia a notificação, lidando com contexto síncrono ou assíncrono """
        coro = self.send_async(
            db,
            user,
            subject,
            message,
            alert_rule_id=alert_rule_id,
            alert_type=alert_type
        )

        try:
            asyncio.get_running_loop()
        except RuntimeError:
            #Sem loop running -> executa de forma síncrona
            asyncio.run(coro)
        else:
            #Dentro de um loop -> retorna a coroutine para ser aguardada
            return coro

    def send_rendered(self, db: Session, user, subject: str, renderer, monitored, alert: dict, alert_rule_id: str | None = None, alert_type: AlertType | None = None) -> None:
        """ Renderiza a mensagem para cada canal e envia a notificação """
        async def _dispatch():
            tasks = []
            for channel in self.channels:
                html = isinstance(channel, EmailChannel)
                #Renderiza texto puro em HTML conforme o canal
                message = renderer(monitored, alert, html=html)
                tasks.append(
                    self._send_one_async(db, user, subject, message, alert_rule_id, channel, alert_type)
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
