""" Configurações específicas do serviço de scraping (MarketScraper).

Este módulo estende `shared.core.config_base.ConfigBase` com opções
próprias do MarketScraper, centralizando parâmetros de cache, limitação
de taxa, delays humanizados e rechecagens. Todos os valores podem ser
configurados via variáveis de ambiente.
"""

import os
from shared.core.config_base import ConfigBase


__all__ = ["Settings", "settings"]

class Settings(ConfigBase):
    """ Conjunto de configurações do MarketScraper.

    Herda de `ConfigBase` e carrega valores a partir de variáveis de
    ambiente, definindo padrões seguros para desenvolvimento. Os campos
    abaixo documentam a finalidade de cada parâmetro.
    """

    #TTL base para o cache de scraping (segundos)
    CACHE_BASE_TTL: int = int(os.getenv("CACHE_BASE_TTL", str(3600)))  #Validade do cache

    #TTL para validação condicional (ETag/Last-Modified), em segundos
    ETAG_CACHE_TTL: int = int(os.getenv("ETAG_CACHE_TTL", "86400"))

    #TTL para assinaturas de conteúdo (hash), em segundos
    SIG_CACHE_TTL: int = int(os.getenv("SIG_CACHE_TTL", "86400"))

    #Parâmetros para o HumanizeDelayManager
    HUMAN_AVG_WPM: int = int(os.getenv("HUMAN_AVG_WPM", "200"))  #Palavras/minuto simuladas
    HUMAN_BASE_DELAY: float = float(os.getenv("HUMAN_BASE_DELAY", "1.0"))  #Atraso inicial (s)
    HUMAN_FATIGUE_MIN: float = float(os.getenv("HUMAN_FATIGUE_MIN", "0.5"))  #Fadiga mínima (fator)
    HUMAN_FATIGUE_MAX: float = float(os.getenv("HUMAN_FATIGUE_MAX", "2.0"))  #Fadiga máxima (fator)

    #Parâmetros do Throttle e Rate Limiter
    THROTTLE_RATE: float = float(os.getenv("THROTTLE_RATE", "0.2"))  #Taxa de consumo de tokens
    THROTTLE_CAPACITY: float = float(os.getenv("THROTTLE_CAPACITY", "3"))  #Capacidade do bucket (tokens)
    JITTER_MIN: float = float(os.getenv("JITTER_MIN", "2.0"))  #Atraso aleatório mínimo adicional (s)
    JITTER_MAX: float = float(os.getenv("JITTER_MAX", "7.0"))  #Atraso aleatório máximo adicional (s)

    MONITORED_RATE_LIMIT: int = int(os.getenv("MONITORED_RATE_LIMIT", "100"))  #Limite de taxa para produtos monitorados (por janela)
    COMPETITOR_SERVICE_RATE_LIMIT: int = int(
        os.getenv("COMPETITOR_SERVICE_RATE_LIMIT", "200")
    )  #Limite de taxa para scraping de concorrentes (por janela)
    RATE_LIMIT_WINDOW: int = int(os.getenv("RATE_LIMIT_WINDOW", "3600"))  #Duração da janela do rate limit (segundos)

    #Intervalo base para o AdaptiveRecheckManager (segundos)
    ADAPTIVE_RECHECK_BASE_INTERVAL: int = int(
        os.getenv("ADAPTIVE_RECHECK_BASE_INTERVAL", "7200")
    )  #Base para reagendamentos

    #Tempo padrão máximo para cada etapa do pipeline (segundos)
    SCRAPER_STEP_TIMEOUT_SECONDS: float = float(
        os.getenv("SCRAPER_STEP_TIMEOUT_SECONDS", "3.0")
    )

    #Tempo máximo global para execução do pipeline (segundos)
    SCRAPER_PIPELINE_TIMEOUT_SECONDS: float = float(
        os.getenv("SCRAPER_PIPELINE_TIMEOUT_SECONDS", "12.0")
    )

    #Limites de segurança para downloads HTTP do scraper
    SCRAPER_HTTP_MAX_REDIRECTS: int = int(os.getenv("SCRAPER_HTTP_MAX_REDIRECTS", "3"))
    SCRAPER_HTTP_MAX_CONTENT_LENGTH: int = int(
        os.getenv("SCRAPER_HTTP_MAX_CONTENT_LENGTH", str(2_000_000))
    ) #~2MB para evitar respostas gigantes
    SCRAPER_HTTP_MAX_CONNECTIONS: int = int(
        os.getenv("SCRAPER_HTTP_MAX_CONNECTIONS", "10")
    )
    SCRAPER_HTTP_MAX_KEEPALIVE: int = int(os.getenv("SCRAPER_HTTP_MAX_KEEPALIVE", "5"))
    SCRAPER_HTTP_TIMEOUT_CONNECT: float = float(
        os.getenv("SCRAPER_HTTP_TIMEOUT_CONNECT", "3.0")
    )
    SCRAPER_HTTP_TIMEOUT_READ: float = float(os.getenv("SCRAPER_HTTP_TIMEOUT_READ", "3.0"))
    SCRAPER_HTTP_TIMEOUT_WRITE: float = float(os.getenv("SCRAPER_HTTP_TIMEOUT_WRITE", "3.0"))
    SCRAPER_HTTP_TIMEOUT_POOL: float = float(os.getenv("SCRAPER_HTTP_TIMEOUT_POOL", "3.0"))

#Instância única de settings para a aplicação
settings = Settings()
