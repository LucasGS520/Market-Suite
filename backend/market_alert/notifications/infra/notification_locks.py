""" Gerenciamento de locks Redis para processamento exclusivo de notificações.

Centraliza as chamadas de acquire/release de locks, mantendo o restante
do código livre de detalhes de infraestrutura de concorrência.
"""

from __future__ import annotations

from shared.utils.redis_locks import acquire_notification_lock, release_notification_lock


class NotificationLockManager:
    """ Gerencia locks Redis para garantir processamento exclusivo de notificações.

    Envolve `acquire_notification_lock` e `release_notification_lock` do shared,
    expondo uma interface coesa e centralizada para o módulo de notificações.
    """

    def acquire(self, dedup_hash: str, *, ttl_seconds: int = 60) -> tuple[bool, str | None]:
        """ Adquire lock de processamento para uma notificação.

        Args:
            dedup_hash: Hash de deduplicação que identifica a notificação.
            ttl_seconds: Tempo de expiração do lock em segundos.

        Returns:
            Tupla (adquirido, lock_owner). Se adquirido=False, lock_owner é None.
        """
        return acquire_notification_lock(dedup_hash, ttl_seconds=ttl_seconds)

    def release(self, dedup_hash: str, lock_owner: str | None) -> bool:
        """ Libera o lock de processamento da notificação.

        Args:
            dedup_hash: Hash de deduplicação da notificação.
            lock_owner: Identificador do dono do lock (retornado no acquire).

        Returns:
            True se o lock foi liberado com sucesso.
        """
        return release_notification_lock(dedup_hash, lock_owner)


# Instância padrão — pode ser substituída em testes por uma instância mock
notification_lock_manager = NotificationLockManager()
