from __future__ import annotations

from abc import ABC, abstractmethod
import asyncio
import structlog

logger = structlog.get_logger("notifications")


class NotificationChannel(ABC):
    """ Interface base de envio de notificações """
    def send(self, user, subject: str, message: str):
        """ Executa ``send_async`` de forma síncrona """
        return asyncio.run(self.send_async(user, subject, message))

    @abstractmethod
    async def send_async(self, user, subject: str, message: str) -> dict | None:
        """ Envia uma notificação ao usuário de forma assíncrona

        Retorna um dicionário com metadados do provedor ou ´None´
        caso não haja informações adicionais
        """
        raise NotImplementedError
