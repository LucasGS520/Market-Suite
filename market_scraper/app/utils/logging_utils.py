""" Utilitário ajudante para registro estruturado """

from __future__ import annotations


def mask_identifier(value: str, visible: int = 4) -> str:
    """ Retorna um identificador parcialmente mascarado para privacidade em logs """
    if not value:
        return value
    if len(value) <= visible * 2:
        return value
    return f"{value[:visible]}***{value[-visible:]}"
