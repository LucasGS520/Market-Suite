"""Regras de domínio para preferências e configurações de usuário."""

from market_alert.enums.enums_notifications import NotificationChannel


#Canais aceitos pela API de preferências globais de notificação.
DEFAULT_NOTIFICATION_CHANNELS = {
    NotificationChannel.email,
    NotificationChannel.push,
    NotificationChannel.sms,
    NotificationChannel.whatsapp,
}
