""" Repositório Redis para marcadores de deduplicação e cooldown de notificações.

Centraliza todas as operações Redis relacionadas a notificações em um único lugar,
eliminando importações espalhadas de shared.utils.redis_client pelo módulo.
"""

from __future__ import annotations

from uuid import UUID

from shared.utils.redis_client import key_exists, set_key_with_ttl

from market_alert.enums.enums_notifications import EventType, NotificationChannel


class NotificationRedisRepository:
    """ Abstração das operações Redis para deduplicação e cooldown de notificações.

    Encapsula a construção de chaves e as chamadas ao cliente Redis,
    mantendo o restante do código livre de detalhes de infraestrutura.
    """

    # --- Métodos de deduplicação ---

    def has_dedup_marker(self, dedup_hash: str) -> bool:
        """ Verifica se existe um marcador de deduplicação ativo para o hash.

        Args:
            dedup_hash: Hash SHA-256 que identifica uma notificação.

        Returns:
            True se o marcador existe (notificação já enviada recentemente).
        """
        return key_exists(self._dedup_key(dedup_hash))

    def set_dedup_marker(self, dedup_hash: str, ttl_seconds: int) -> bool:
        """ Registra um marcador de deduplicação com TTL.

        Usa SET NX (only_if_absent) para garantir que apenas o primeiro
        processo a definir o marcador vence (prevenção de race condition).

        Args:
            dedup_hash: Hash SHA-256 da notificação.
            ttl_seconds: Tempo de expiração em segundos.

        Returns:
            True se o marcador foi criado. False se já existia (duplicata).
        """
        result = set_key_with_ttl(
            self._dedup_key(dedup_hash),
            "1",
            ttl_seconds,
            only_if_absent=True,
        )
        return result is not False

    # --- Métodos de cooldown ---

    def has_cooldown_marker(
        self,
        *,
        monitored_product_id: UUID | None,
        channel: NotificationChannel,
        event_type: EventType,
    ) -> bool:
        """ Verifica se o cooldown está ativo para a combinação produto/canal/evento.

        Args:
            monitored_product_id: ID do produto monitorado.
            channel: Canal de notificação.
            event_type: Tipo de evento.

        Returns:
            True se o cooldown está ativo (deve suprimir nova notificação).
        """
        return key_exists(
            self._cooldown_key(
                monitored_product_id=monitored_product_id,
                channel=channel,
                event_type=event_type,
            )
        )

    def set_cooldown_marker(
        self,
        *,
        monitored_product_id: UUID | None,
        channel: NotificationChannel,
        event_type: EventType,
        ttl_seconds: int,
    ) -> bool:
        """ Registra um marcador de cooldown com TTL.

        Args:
            monitored_product_id: ID do produto monitorado.
            channel: Canal de notificação.
            event_type: Tipo de evento.
            ttl_seconds: Tempo de expiração do cooldown em segundos.

        Returns:
            True se o marcador foi registrado com sucesso.
        """
        result = set_key_with_ttl(
            self._cooldown_key(
                monitored_product_id=monitored_product_id,
                channel=channel,
                event_type=event_type,
            ),
            "1",
            ttl_seconds,
        )
        return result is not False

    # --- Construção de chaves ---

    def _dedup_key(self, dedup_hash: str) -> str:
        """ Monta a chave Redis para marcador de deduplicação """
        return f"notifications:dedup:{dedup_hash}"

    def _cooldown_key(
        self,
        *,
        monitored_product_id: UUID | None,
        channel: NotificationChannel,
        event_type: EventType,
    ) -> str:
        """ Monta a chave Redis para marcador de cooldown por produto/canal/evento """
        product_value = str(monitored_product_id) if monitored_product_id else "global"
        return f"notifications:cooldown:{product_value}:{channel.value}:{event_type.value}"


# Instância padrão — pode ser substituída em testes por uma instância mock
notification_redis_repository = NotificationRedisRepository()
