""" Registro de adaptadores de canais de notificação """

from __future__ import annotations

from market_alert.enums.enums_notifications import NotificationChannel
from market_alert.notifications.channels.base import ChannelAdapter
from market_alert.notifications.channels.email_adapter import EmailAdapter
from market_alert.notifications.channels.push_adapter import PushAdapter
from market_alert.notifications.channels.sms_adapter import SmsAdapter
from market_alert.notifications.channels.webhook_adapter import WebhookAdapter
from market_alert.notifications.channels.whatsapp_adapter import WhatsappAdapter


_ADAPTERS: dict[NotificationChannel, ChannelAdapter] = {
    NotificationChannel.email: EmailAdapter(),
    NotificationChannel.sms: SmsAdapter(),
    NotificationChannel.whatsapp: WhatsappAdapter(),
    NotificationChannel.push: PushAdapter(),
    NotificationChannel.webhook: WebhookAdapter(),
}

def get_channel_adapter(channel: NotificationChannel) -> ChannelAdapter:
    """ Retorna o adaptador configurado para o canal informado """
    adapter = _ADAPTERS.get(channel)
    if adapter is None:
        raise ValueError(f"Canal não suportado: {channel}")
    return adapter
