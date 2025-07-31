""" Gerenciador de envio de alertas

Recebe uma lista de canais e repassa as
notificações a cada um deles.
"""

from __future__ import annotations

from typing import Iterable, List, TYPE_CHECKING
from uuid import UUID

if TYPE_CHECKING:
    from app.models.models_alerts import AlertRule

from datetime import datetime, timezone
import asyncio
import time

import structlog
from sqlalchemy.orm import Session

from app.crud.crud_user import get_user_by_id
from app.crud.crud_alert_rules import update_last_notified, get_alert_rules_or_default, get_active_alert_rules_for_product as crud_get_active_rules
from app.crud.crud_notification_logs import create_notification_log, has_recent_duplicate_notification
from .matching import alert_matches_rule
from .templates import render_price_alert, render_price_change_alert, render_listing_alert, render_error_alert

from .channels import NotificationChannel
from .channels.email import EmailChannel
from .channels.sms import SMSChannel
from .channels.push import PushChannel
from .channels.whatsapp import WhatsAppChannel
from .channels.slack import SlackChannel

from app.enums.enums_alerts import ChannelType, AlertType
from app.core.config import settings
from app import metrics

logger = structlog.get_logger("alerts")


def __verify_channel_settings() -> dict:
    """  Verifica as configurações necessárias para todos os canais de notificação

    Retorna um mapeamento do nome do canal para variáveis e "logs" de ambiente
    ausente e um aviso para cada entrada encontrada
    """
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
        logger.warning("channel_vars_missing", channel=channel, missing=vars_missing)
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

def dispatch_price_alerts(db, monitored_product, alerts: list, manager: NotificationManager | None = None) -> None:
    """ Envia alertas de preço para um produto monitorado """
    user = get_user_by_id(db, monitored_product.user_id)
    if manager is None:
        manager = get_notification_manager()

    if not getattr(user, "notifications_enabled", True):
        metrics.NOTIFICATIONS_SKIPPED_TOTAL.labels(reason="disabled").inc()
        return

    try:
        #Recupera regras ativas ou um padrão caso nenhuma exista
        rules = get_alert_rules_or_default(db, user.id, monitored_product.id)
    except AttributeError:
        from types import SimpleNamespace

        rules = [
            SimpleNamespace(
                id=None,
                rule_type=AlertType.PRICE_TARGET,
                threshold_value=None,
                threshold_percent=None,
                target_price=None,
                product_status=None,
                enabled=True,
                last_notified_at=None
            )
        ]

    now = datetime.now(timezone.utc)
    cooldown = settings.ALERT_RULE_COOLDOWN

    filtered: list[tuple[dict, AlertRule]] = []
    #Para cada alerta gerado checamos as regras configuradas
    for alert in alerts:
        for rule in rules:

            if alert_matches_rule(alert, rule):
                metrics.ALERT_RULES_TRIGGERED_TOTAL.labels(rule_type=rule.rule_type.value).inc()
                last_sent = getattr(rule, "last_notified_at", None)

                if last_sent and (now - last_sent).total_seconds() < cooldown:
                    metrics.ALERT_RULES_SUPPRESSED_TOTAL.labels(reason="cooldown").inc()
                    break

                rule_id = str(rule.id) if getattr(rule, "id", None) else None
                alert = {**alert, "rule_id": rule_id}
                filtered.append((alert, rule))
                break

    #Envia efetivamente as notificações com o template correto
    for alert, rule in filtered:
        template = render_price_alert
        alert_type = AlertType.PRICE_TARGET

        if alert.get("type") in ("price_increase", "price_decrease"):
            template = render_price_change_alert
            alert_type = AlertType.PRICE_CHANGE

        elif alert.get("status") in ("unavailable", "removed"):
            template = render_listing_alert
            alert_type = AlertType.LISTING_PAUSED if alert.get("status") == "unavailable" else AlertType.LISTING_REMOVED

        elif alert.get("error") or alert.get("detail"):
            template = render_error_alert
            alert_type = AlertType.SCRAPING_ERROR

        subject = f"Alerta {alert_type.value.replace('_', ' ')} - {monitored_product.name_identification}"
        preview = template(monitored_product, alert)

        duplicate = False
        if db is not None:
            #Evita disparos repetidos em curta janela
            duplicate = has_recent_duplicate_notification(
                db, user.id, subject, preview, settings.ALERT_DUPLICATE_WINDOW
            )
        if not duplicate:
            manager.send_rendered(
                db,
                user,
                subject,
                template,
                monitored_product,
                alert,
                alert_rule_id=alert.get("rule_id"),
                alert_type=alert_type
            )
            if db is not None:
                #Registra horário do envio para controle de cooldown
                update_last_notified(db, alert.get("rule_id"), now)
        else:
            metrics.ALERT_RULES_SUPPRESSED_TOTAL.labels(reason="duplicate").inc()
