""" Normalização de preços: string/número bruto → Decimal canônico. """

from __future__ import annotations

from decimal import Decimal
from typing import Any

import structlog

from market_scraper.utils.price import parse_price_str

logger = structlog.get_logger("price_normalizer")


class PriceNormalizer:
    """ Converte valores brutos de preço em Decimal; retorna None em falha."""

    def normalize(self, raw_price: Any, url: str) -> Decimal | None:
        if raw_price is None:
            return None
        try:
            return parse_price_str(raw_price, url)
        except Exception:
            logger.debug("price_normalizer_parse_failed", raw=str(raw_price)[:50], url=url)
            return None


__all__ = ["PriceNormalizer"]
