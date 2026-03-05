""" Constantes de domínio para o módulo de notificações.

Centraliza valores que antes estavam espalhados entre CRUD, evaluator e service layer.
"""

from __future__ import annotations

from market_alert.enums.enums_notifications import NotificationChannel

#Número máximo de tentativas de entrega por notificação
DEFAULT_MAX_ATTEMPTS: int = 3

#Janela mínima de deduplicação de envios (10 minutos em segundos)
DEFAULT_DEDUPE_SENT_WINDOW_SECONDS: int = 60 * 10

#Canais habilitados por padrão ao criar um novo usuário
# A estrutura é derivada do Enum para reduzir risco de inconsistência quando novos canais forem adicionados
DEFAULT_CHANNEL_ENABLED: dict[NotificationChannel, bool] = {
    channel: channel == NotificationChannel.email
    for channel in NotificationChannel
}
