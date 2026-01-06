""" Contratos básicos para adaptadores de canais de notificação """

from __future__ import annotations

from typing import Any, Protocol


class ChannelAdapter(Protocol):
    """ Interface base para envio de notificações por canal """
    
    def send(self, payload: dict[str, Any]) -> tuple[bool, dict[str, Any] | None, str | None]:
        """ Envia o payload e retorna sucesso, resposta e código de erro """
        raise NotImplementedError
    