""" Encapsulamento de infraestrutura externa para notificações (Redis, locks) 

Expõe componentes externos (locks, Redis e adaptadores de canal) necessários
para integração, mantendo o restante dos detalhes interno ao subpacote.
"""

from market_alert.notifications.infra.channels import get_channel_adapter
from market_alert.notifications.infra.notification_locks import NotificationLockManager
from market_alert.notifications.infra.redis_repository import NotificationRedisRepository

__all__ = [
    "NotificationLockManager",
    "NotificationRedisRepository",
    "get_channel_adapter",
]
