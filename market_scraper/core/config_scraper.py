""" Define parâmetros de configuração do serviço MarketScraper.

O módulo mantém apenas controles numéricos necessários para ajustar
timeouts e limites do fluxo determinístico. Flags de alternância de
implementação foram removidas para reduzir variabilidade operacional,
mantendo comportamento documentado como único caminho suportado.
"""

from __future__ import annotations

import os

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

    SCRAPER_HTTP_TIMEOUT_CONNECT: float = float(
        os.getenv("SCRAPER_HTTP_TIMEOUT_CONNECT", "3.0")
    ) #Tempo de conexão HTTP individual
    SCRAPER_HTTP_TIMEOUT_READ: float = float(
        os.getenv("SCRAPER_HTTP_TIMEOUT_READ", "3.0")
    ) #Tempo máximo de leitura por requisição
    SCRAPER_HTTP_TIMEOUT_WRITE: float = float(
        os.getenv("SCRAPER_HTTP_TIMEOUT_WRITE", "3.0")
    ) #Tempo máximo de escrita/envio
    SCRAPER_HTTP_TIMEOUT_POOL: float = float(
        os.getenv("SCRAPER_HTTP_TIMEOUT_POOL", "3.0")
    ) #Tempo máximo de espera por conexão no pool

    SCRAPER_HTTP_RETRIES: int = int(
        os.getenv("SCRAPER_HTTP_RETRIES", "2")
    ) #Tentativas extras para downloads HTTP
    SCRAPER_HTTP_RETRY_BACKOFF_BASE: float = float(
        os.getenv("SCRAPER_HTTP_RETRY_BACKOFF_BASE", "0.5")
    ) #Base do backoff exponencial
    
    SCRAPER_HTTP_MAX_REDIRECTS: int = int(
        os.getenv("SCRAPER_HTTP_MAX_REDIRECTS", "3")
    ) #Limite de redirecionamentos seguidos
    SCRAPER_HTTP_MAX_CONNECTIONS: int = int(
        os.getenv("SCRAPER_HTTP_MAX_CONNECTIONS", "10")
    ) #Máximo de conexões simultâneas no client
    SCRAPER_HTTP_MAX_KEEPALIVE: int = int(
        os.getenv("SCRAPER_HTTP_MAX_KEEPALIVE", "5")
    ) #Conexões mantidas em keep-alive
    SCRAPER_HTTP_MAX_CONTENT_LENGTH: int = int(
        os.getenv("SCRAPER_HTTP_MAX_CONTENT_LENGTH", "2000000")
    ) #Tamanho máximo aceito para payloads HTTP

    SCRAPER_SINGLEFLIGHT_LOCK_TTL: float = float(
        os.getenv("SCRAPER_SINGLEFLIGHT_LOCK_TTL", "15.0")
    ) #TTL dos locks de singleflight
    
    SCRAPER_PRICE_TOLERANCE: float = float(
        os.getenv("SCRAPER_PRICE_TOLERANCE", "0.0")
    ) #Tolerância percentual para comparação de preços


#Instância única de settings para a aplicação
settings = Settings()
