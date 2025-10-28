""" Tipos auxiliares compartilhados entre seviços de scraping """

from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class ScrapeResult:
    """ Representa o resultado do processamento de uma coleta """
    status: str
    product_id: str | None = None
    price_changed: bool = False
    http_status: int | None = None
    error_code: str | None = None
    retry_after: int | None = None
    