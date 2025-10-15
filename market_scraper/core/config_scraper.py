""" Define parâmetros de configuração do serviço MarketScraper.

O módulo mnatém apenas controles numéricos necessários para ajustar
timeouts e limites do fluxo determinístico. Flags de alternância de
implementação foram removidas para reduzir variabilidade operacional,
mantendo comportamento documentado como único caminho suportado.
"""

from __future__ import annotations

import os
from typing import ClassVar

from shared.core.config_base import ConfigBase


__all__ = ["Settings", "settings"]

class Settings(ConfigBase):
    """ Organiza configurações essenciais do MarketScraper enxuto """

    # --- Configurações essenciais do pipeline ---
    #Mantemos somente parâmetros numéricos que modulam comportamento único
    SCRAPER_CACHE_TTL_SECONDS: int = int(
        os.getenv("SCRAPER_CACHE_TTL_SECONDS", "3600")
    ) #TTL padrão por URL (segundos)
    SCRAPER_CACHE_MAX_ENTRIES: int = int(
        os.getenv("SCRAPER_CACHE_MAX_ENTRIES", "5000")
    ) #Limites de itens no cache em memória

    SCRAPER_STEP_TIMEOUT_SECONDS: float = float(
        os.getenv("SCRAPER_STEP_TIMEOUT_SECONDS", "8.0")
    ) #Tempo máximo por etapa
    SCRAPER_PIPELINE_TIMEOUT_SECONDS: float = float(
        os.getenv("SCRAPER_PIPELINE_TIMEOUT_SECONDS", "20.0")
    ) #Tempo máximo do pipeline completo

    SCRAPER_ROBOTS_FALLBACK: str = os.getenv(
        "SCRAPER_ROBOTS_FALLBACK",
        "allow",
    ) #Política de fallback para robots.txt

    SCRAPER_HTTP_RETRIES: int = int(
        os.getenv("SCRAPER_HTTP_RETRIES", "2")
    ) #Tentativas extras para downloads HTTP
    SCRAPER_HTTP_RETRY_BACKOFF_BASE: float = float(
        os.getenv("SCRAPER_HTTP_RETRY_BACKOFF_BASE", "0.5")
    ) #Base do backoff exponencial
    
    SCRAPER_SINGLEFLIGHT_LOCK_TTL: float = float(
        os.getenv("SCRAPER_SINGLEFLIGHT_LOCK_TTL", "15.0")
    ) #TTL dos locks de singleflight
    
    SCRAPER_PRICE_TOLERANCE: float = float(
        os.getenv("SCRAPER_PRICE_TOLERANCE", "0.0")
    ) #Tolerância percentual para comparação de preços


#Instância única de settings para a aplicação
settings = Settings()
