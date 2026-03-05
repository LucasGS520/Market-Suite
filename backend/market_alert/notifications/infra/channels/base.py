""" Contratos básicos para adaptadores de canais de notificação """

from __future__ import annotations

from typing import Any, Protocol


class ChannelAdapter(Protocol):
    """ Interface base para envio de notificações por canal """
    
    def send(self, payload: dict[str, Any]) -> dict[str, Any]:
        """ Envia o payload e retorna estrutura com sucesso, ids e erros """
        raise NotImplementedError
    