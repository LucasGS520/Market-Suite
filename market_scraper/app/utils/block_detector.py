""" Funções para identificar bloqueios em respostas HTTP """

from typing import Optional
import requests

from app.enums.enums_block_results import BlockResult


def detect_block(response: Optional[requests.Response]) -> BlockResult:
    """ Retorna o tipo de bloqueio detectado em uma resposta HTTP """
    if response is None:
        return BlockResult.UNKNOWN

    text = response.text.lower() if getattr(response, "text", None) else ""
    if "captcha" in text or "digite os caracteres" in text:
        return BlockResult.CAPTCHA

    if response.status_code == 429:
        return BlockResult.HTTP_429

    if response.status_code == 403:
        return BlockResult.HTTP_403

    return BlockResult.OK
