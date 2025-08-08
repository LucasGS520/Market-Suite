""" Carrega variáveis de ambiente para o serviço de scraping

Este módulo estende as configurações compartilhadas em
`core.config_base`, adicionando apenas parâmetros específicos
do `market_scraper`.
"""

import os
from core.config_base import ConfigBase


__all__ = ["Settings", "settings"]

class Settings(ConfigBase):
    """ Configurações específicas do serviço de scraping """

    #TTL base do cache de scraping
    CACHE_BASE_TTL: int = int(os.getenv("CACHE_BASE_TTL", str(3600)))

    #Parâmetros para o HumanizedDelayManager
    HUMAN_AVG_WPM: int = int(os.getenv("HUMAN_AVG_WPM", "200"))
    HUMAN_BASE_DELAY: float = float(os.getenv("HUMAN_BASE_DELAY", "1.0"))
    HUMAN_FATIGUE_MIN: float = float(os.getenv("HUMAN_FATIGUE_MIN", "0.5"))
    HUMAN_FATIGUE_MAX: float = float(os.getenv("HUMAN_FATIGUE_MAX", "2.0"))

    #Parametros do Throttle e Rate Limiter
    THROTTLE_RATE: float = float(os.getenv("THROTTLE_RATE", "0.2"))
    THROTTLE_CAPACITY: float = float(os.getenv("THROTTLE_CAPACITY", "3"))
    JITTER_MIN: float = float(os.getenv("JITTER_MIN", "2.0"))
    JITTER_MAX: float = float(os.getenv("JITTER_MAX", "7.0"))

    MONITORED_RATE_LIMIT: int = int(os.getenv("MONITORED_RATE_LIMIT", "100"))
    COMPETITOR_SERVICE_RATE_LIMIT: int = int(
        os.getenv("COMPETITOR_SERVICE_RATE_LIMIT", "200")
    )
    RATE_LIMIT_WINDOW: int = int(os.getenv("RATE_LIMIT_WINDOW", "3600"))

    #Parametros do Playwright
    PLAYWRIGHT_HEADLESS: bool = os.getenv("PLAYWRIGHT_HEADLESS", "1") == "1"
    PLAYWRIGHT_TIMEOUT: int = int(os.getenv("PLAYWRIGHT_TIMEOUT", "30000"))

    #Intervalo base para o AdaptiveRecheckManager
    ADAPTIVE_RECHECK_BASE_INTERVAL: int = int(
        os.getenv("ADAPTIVE_RECHECK_BASE_INTERVAL", "7200")
    )

#Instância única de settings para a aplicação
settings = Settings()
