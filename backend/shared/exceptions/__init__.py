"""Exceções compartilhadas entre os serviços.

Este pacote é reutilizado por `market_alert`, `market_orchestrator` e `market_scraper`
para padronizar erros de scraping ou orquestração serializáveis.
"""

from shared.exceptions.temporal import TemporalConnectionError, TemporalUnavailableError
from shared.exceptions.scraper import ScraperError


__all__ = [
    "TemporalConnectionError",
    "TemporalUnavailableError",
    "ScraperError",
]
