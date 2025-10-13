""" Define parâmetros de configuração do serviço MarketScraper.

O módulo estende ``ConfigBase`` com opções próprias do MarketScraper e
centraliza ajustes de cache, limites de taxa, atrasos humanizados e timeouts.
Todos os valores podem ser controlados via variáveis de ambiente para
facilitar tunning em diferentes ambientes.
"""

import os
from shared.core.config_base import ConfigBase


__all__ = ["Settings", "settings"]

class Settings(ConfigBase):
    """ Agrupa valores padrão e tunáveis do MarketScraper """

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

    #Controle geral de cache do pipeline simplificado
    SCRAPER_CACHE_ENABLED: bool = os.getenv("SCRAPER_CACHE_ENABLED", "1").lower() in {
        "1",
        "True",
        "true",
        "on",
        "yes",
    }
    SCRAPER_CACHE_TTL_SECONDS: int = int(
        os.getenv("SCRAPER_CACHE_TTL_SECONDS", str(3600))
    ) #TTL padrão por URL (segundos)
    SCRAPER_CACHE_BACKEND: str = os.getenv("SCRAPER_CACHE_BACKEND", "memory")  #Backend de cache (memory, redis)

    SCRAPER_CACHE_MAX_ENTRIES: int = int(
        os.getenv("SCRAPER_CACHE_MAX_ENTRIES", "5000")
    ) #Limita o número de itens mantidos em memória

    SCRAPER_CACHE_ENVICTION_POLICY: str = os.getenv(
        "SCRAPER_CACHE_ENVICTION_POLICY", 
        "lru",
    ) #Define a política de remoção; flags que controlam comportamento futuro

    #Tempo padrão máximo para cada etapa do pipeline (segundos)
    SCRAPER_STEP_TIMEOUT_SECONDS: float = float(
        os.getenv("SCRAPER_STEP_TIMEOUT_SECONDS", "8.0")
    )

    #Tempo máximo global para execução do pipeline (segundos)
    SCRAPER_PIPELINE_TIMEOUT_SECONDS: float = float(
        os.getenv("SCRAPER_PIPELINE_TIMEOUT_SECONDS", "20.0")
    )

    #Limites de segurança para downloads HTTP do scraper
    SCRAPER_HTTP_MAX_REDIRECTS: int = int(os.getenv("SCRAPER_HTTP_MAX_REDIRECTS", "3"))
    SCRAPER_HTTP_MAX_CONTENT_LENGTH: int = int(
        os.getenv("SCRAPER_HTTP_MAX_CONTENT_LENGTH", str(2_000_000))
    )
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

    #Novos ajustes para robustez dos utilitários (mantém compatibilidade da API pública)
    SCRAPER_ROBOTS_FALLBACK: str = os.getenv("SCRAPER_ROBOTS_FALLBACK", "allow") #Permite fallback configurável para robots.txt
    SCRAPER_HTTP_RETRIES: int = int(os.getenv("SCRAPER_HTTP_RETRIES", "2")) #Quantidade padrão de tentativas extras
    SCRAPER_HTTP_RETRY_BACKOFF_BASE: float = float(
        os.getenv("SCRAPER_HTTP_RETRY_BACKOFF_BASE", "0.5")
    ) #Base do backoff exponencial para downloads
    SCRAPER_DNS_TIMEOUT: float = float(
        os.getenv("SCRAPER_DNS_TIMEOUT", "2")
    ) #Timeout da resolução DNS para evitar bloqueios longos
    SCRAPER_USE_PRICE_PARSER: bool = os.getenv("SCRAPER_USE_PRICE_PARSER", "0").lower() in {
        "1",
        "True",
        "true",
        "on",
        "yes",
    } #Flag para habilitar integração opcional com price-parser
    SCRAPER_SINGLEFLIGHT_ENABLED: bool = os.getenv("SCRAPER_SINGLEFLIGHT_ENABLED", "1").lower() in {
        "1",
        "True",
        "true",
        "on",
        "yes",
    } #Flag para habilitar coalescing de downloads simultâneos

#Instância única de settings para a aplicação
settings = Settings()
