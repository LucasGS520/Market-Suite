""" Validação de qualidade mínima de HTML para extração de produto.

Critérios canônicos definidos em requisitos_ideais_scraper.md:
  1. Status HTTP 2xx (quando fornecido)
  2. Corpo >= 1200 bytes (UTF-8)
  3. Ausência de marcador forte de bloqueio anti-bot
  4. Mínimo 2 sinais de produto identificáveis
"""

from __future__ import annotations

import re

#Marcadores que invalidam extração — página ainda é uma página de bloqueio
_RE_ANTI_BOT_STRONG = re.compile(
    r"__cf_chl"
    r"|verify\s+you\s+are\s+human"
    r"|<[^>]*class=['\"][^'\"]*captcha"
    r"|hcaptcha\.com/1"
    r"|cf-browser-verification"
    r"|enable\s+javascript\s+to\s+continue",
    re.IGNORECASE,
)

#Sinais de produto — cada padrão conta 1 ponto
_RE_JSON_LD_PRODUCT = re.compile(r'"@type"\s*:\s*"Product"', re.IGNORECASE)
_RE_OFFER = re.compile(r'"@type"\s*:\s*"Offer"', re.IGNORECASE)
_RE_PRICE = re.compile(
    r'itemprop=["\']price["\']'
    r'|"price"\s*:\s*["\'\d]'
    r'|property=["\']product:price'
    r'|class=["\'][^"\']*\bprice\b[^"\']*["\']',
    re.IGNORECASE,
)
_RE_TITLE = re.compile(
    r'itemprop=["\']name["\']'
    r'|og:title'
    r'|"name"\s*:\s*"',
    re.IGNORECASE,
)
_RE_AVAILABILITY = re.compile(
    r'itemprop=["\']availability["\']'
    r'|"availability"\s*:'
    r'|\badd[_-]?to[_-]?cart\b'
    r'|\bcomprar\b',
    re.IGNORECASE,
)

_MIN_HTML_BYTES = 1_200
_MIN_PRODUCT_SIGNALS = 2


def is_html_useful(html: str | None, http_status: int | None) -> bool:
    """ Verifica se o HTML atende ao critério mínimo para tentativa de extração.

    Args:
        html: Conteúdo HTML bruto. ``None`` retorna ``False`` imediatamente.
        http_status: Código HTTP recebido. ``None`` pula verificação de status.

    Returns:
        ``True`` se o HTML passa em todos os critérios canônicos; ``False`` caso contrário.
    """
    if html is None:
        return False

    if http_status is not None and not (200 <= http_status < 300):
        return False

    if len(html.encode("utf-8", errors="replace")) < _MIN_HTML_BYTES:
        return False

    if _RE_ANTI_BOT_STRONG.search(html):
        return False

    signals = (
        bool(_RE_JSON_LD_PRODUCT.search(html))
        + bool(_RE_OFFER.search(html))
        + bool(_RE_PRICE.search(html))
        + bool(_RE_TITLE.search(html))
        + bool(_RE_AVAILABILITY.search(html))
    )
    return signals >= _MIN_PRODUCT_SIGNALS


__all__ = ["is_html_useful"]
