""" Resolução de destino e confirmação de canal de notificação.

Funções puras — sem I/O, sem efeitos colaterais.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from market_alert.enums.enums_notifications import NotificationChannel

if TYPE_CHECKING:
    from market_alert.models import User, UserNotificationPreference


def resolve_channel_destination(
    preference: "UserNotificationPreference | None",
    *,
    user: "User",
    channel: NotificationChannel,
) -> str | None:
    """ Determina o endereço de destino do canal, respeitando preferências do usuário.

    Prioridade:
    1. Destino customizado na preferência do usuário
    2. Email do usuário (para canal email)
    3. Telefone do usuário (para SMS/WhatsApp)

    Args:
        preference: Preferência de notificação do usuário para o canal.
        user: Usuário dono da notificação.
        channel: Canal de entrega.

    Returns:
        String com o destinatário, ou None se não houver destino válido.
    """
    if preference and preference.destination:
        return preference.destination

    if channel == NotificationChannel.email:
        return user.email
    if channel in {NotificationChannel.sms, NotificationChannel.whatsapp}:
        return user.phone_number

    return None


def is_channel_confirmed(
    *,
    channel: NotificationChannel,
    user: "User",
    preference: "UserNotificationPreference | None",
) -> bool:
    """ Verifica se o contato do canal está confirmado e validado para envio.

    Regras por canal:
    - email: exige `email_verified=True` no usuário
    - sms/whatsapp: exige campo `confirmed=True` nos metadados da preferência
    - demais canais: considerados confirmados por padrão

    Args:
        channel: Canal a verificar.
        user: Usuário dono da notificação.
        preference: Preferência de notificação do usuário para o canal.

    Returns:
        True se o canal está confirmado para envio.
    """
    if channel == NotificationChannel.email:
        return user.email_verified
    if channel in {NotificationChannel.sms, NotificationChannel.whatsapp}:
        if preference and isinstance(preference.channel_metadata, dict):
            return bool(preference.channel_metadata.get("confirmed"))
        return False
    return True
