""" Configurações específicas do serviço de scraping

Este módulo complementa ``shared.core.config_base`` com opções
próprias do ``market_scraper``
"""

import os
from shared.core.config_base import ConfigBase


__all__ = ["Settings", "settings"]

class Settings(ConfigBase):
    """ Configurações específicas do serviço de scraping """

    #TTL base do cache de scraping
    CACHE_BASE_TTL: int = int(os.getenv("CACHE_BASE_TTL", str(3600))) #Validade do cache

    #TTL para cabeçalhos ETag/Last-Modified
    ETAG_CACHE_TTL: int = int(os.getenv("ETAG_CACHE_TTL", "86400"))

    #TTL para assinaturas de conteúdo
    SIG_CACHE_TTL: int = int(os.getenv("SIG_CACHE_TTL", "86400"))

    #Parâmetros para o HumanizedDelayManager
    HUMAN_AVG_WPM: int = int(os.getenv("HUMAN_AVG_WPM", "200")) #Palavras/minuto simuladas
    HUMAN_BASE_DELAY: float = float(os.getenv("HUMAN_BASE_DELAY", "1.0")) #Atraso incial
    HUMAN_FATIGUE_MIN: float = float(os.getenv("HUMAN_FATIGUE_MIN", "0.5")) #Fadiga mínima
    HUMAN_FATIGUE_MAX: float = float(os.getenv("HUMAN_FATIGUE_MAX", "2.0")) #Fadiga máxima

    #Parametros do Throttle e Rate Limiter
    THROTTLE_RATE: float = float(os.getenv("THROTTLE_RATE", "0.2")) #Taxa de consumo de tokens
    THROTTLE_CAPACITY: float = float(os.getenv("THROTTLE_CAPACITY", "3")) # Capacidade do bucket
    JITTER_MIN: float = float(os.getenv("JITTER_MIN", "2.0")) #Delay mínimo adicional
    JITTER_MAX: float = float(os.getenv("JITTER_MAX", "7.0")) #Delay máximo adicional

    MONITORED_RATE_LIMIT: int = int(os.getenv("MONITORED_RATE_LIMIT", "100")) #Limite de produtos monitorados
    COMPETITOR_SERVICE_RATE_LIMIT: int = int(
        os.getenv("COMPETITOR_SERVICE_RATE_LIMIT", "200")
    ) #Limite para serviços de concorrentes
    RATE_LIMIT_WINDOW: int = int(os.getenv("RATE_LIMIT_WINDOW", "3600")) #Janela de rate limit

    #Intervalo base para o AdaptiveRecheckManager
    ADAPTIVE_RECHECK_BASE_INTERVAL: int = int(
        os.getenv("ADAPTIVE_RECHECK_BASE_INTERVAL", "7200")
    ) #Base para reagendamentos

#Instância única de settings para a aplicação
settings = Settings()
