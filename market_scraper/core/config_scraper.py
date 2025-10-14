""" Define parâmetros de configuração do serviço MarketScraper.

O módulo agrupa variáveis essenciais que o pipeline utiliza por padrão e
mantém um bloco separado com ajustes avançados que passaram a ser opt-in.
Os valores seguem lidos de variáveis de ambiente para facilitar tunning por
ambiente sem alterar código.
"""

from __future__ import annotations

import os
from typing import ClassVar

from shared.core.config_base import ConfigBase


__all__ = ["Settings", "settings"]

class Settings(ConfigBase):
    """ Organiza configurações essenciais e avançadas do MarketScraper """

    # --- Configurações essenciais do pipeline ---
    #Mantemos somente o que impacta diretamente o caminho padrão
    SCRAPER_CACHE_ENABLED: bool = os.getenv("SCRAPER_CACHE_ENABLED", "1").lower() in {
        "1",
        "True",
        "true",
        "on",
        "yes",
    }
    SCRAPER_CACHE_TTL_SECONDS: int = int(
        os.getenv("SCRAPER_CACHE_TTL_SECONDS", "3600")
    ) #TTL padrão por URL (segundos)
    SCRAPER_CACHE_BACKEND: str = os.getenv(
        "SCRAPER_CACHE_BACKEND",
        "memory",
    ) #Backend padrão mantém LRU em memória
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
    SCRAPER_ROBOTS_PARSER: str = os.getenv(
        "SCRAPER_ROBOTS_PARSER",
        "urllib",
    ) #Parser padrão mantém urllib como baseline suportado

    SCRAPER_HTTP_RETRIES: int = int(
        os.getenv("SCRAPER_HTTP_RETRIES", "2")
    ) #Tentativas extras para downloads HTTP
    SCRAPER_HTTP_RETRY_BACKOFF_BASE: float = float(
        os.getenv("SCRAPER_HTTP_RETRY_BACKOFF_BASE", "0.5")
    ) #Base do backoff exponencial

    SCRAPER_USE_PRICE_PARSER: bool = os.getenv(
        "SCRAPER_USE_PRICE_PARSER",
        "0",
    ).lower() in {"1", "True", "true", "on", "yes"} #Adapter price-parser é opt-in
    SCRAPER_SINGLEFLIGHT_ENABLED: bool = os.getenv(
        "SCRAPER_SINGLEFLIGHT_ENABLED",
        "1",
    ).lower() in {"1", "True", "true", "on", "yes"}  #Coalescing ativo no fluxo padrão
    
    SCRAPER_SINGLEFLIGHT_LOCK_TTL: float = float(
        os.getenv("SCRAPER_SINGLEFLIGHT_LOCK_TTL", "15.0")
    )  #TTL dos locks de singleflight
    
    SCRAPER_PRICE_TOLERANCE: float = float(
        os.getenv("SCRAPER_PRICE_TOLERANCE", "0.0")
    )  #Tolerância percentual para comparação de preços


#Instância única de settings para a aplicação
settings = Settings()
