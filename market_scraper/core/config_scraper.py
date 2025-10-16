""" Define parâmetros de configuração do serviço MarketScraper.

O módulo mantém apenas controles numéricos necessários para ajustar
timeouts e limites do fluxo determinístico. Flags de alternância de
implementação foram removidas para reduzir variabilidade operacional,
mantendo comportamento documentado como único caminho suportado.

As novas chaves relacionadas a headers e User-Agent foram adicionadas
para centralizar o comportamento descrito na iniciativa de rotação de
identidade do scraper, permitindo ajustes finos sem alterar o código.
"""

from __future__ import annotations

import os
from typing import Tuple

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

    SCRAPER_DNS_TIMEOUT: float = float(
        os.getenv("SCRAPER_DNS_TIMEOUT", "2.0")
    ) #Tempo limite das resoluções DNS seguras
    SCRAPER_DNS_CACHE_TTL: float = float(
        os.getenv("SCRAPER_DNS_CACHE_TTL", "120.0")
    ) #Tempo em segundos que respostas DNS permanecem em cache

    # ----- Configurações de headers e User-Agent -----
    #Centralizamos valores realistas para reduzir bloqueios em sites comuns
    _DEFAULT_UA_POOL: Tuple[str, ...] = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 "
        "(KHTML, like Gecko) Version/17.0 Safari/605.1.15",
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/122.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:124.0) Gecko/20100101 Firefox/124.0",
        "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 "
        "(KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1",
    )

    SCRAPER_USER_AGENT_STATIC_POOL: Tuple[str, ...] = tuple(
        ua.strip()
        for ua in os.getenv("SCRAPER_USER_AGENT_STATIC_POOL", "||".join(_DEFAULT_UA_POOL)).split("||")
        if ua.strip()
    ) #Pool curado de User-Agents realistas
    SCRAPER_USER_AGENT_DEFAULT: str = os.getenv(
        "SCRAPER_USER_AGENT_DEFAULT",
        SCRAPER_USER_AGENT_STATIC_POOL[0] if SCRAPER_USER_AGENT_STATIC_POOL else _DEFAULT_UA_POOL[0],
    ) #UA padrão utilizado em fallbacks
    SCRAPER_USER_AGENT_ROTATION_STRATEGY: str = os.getenv(
        "SCRAPER_USER_AGENT_ROTATION_STRATEGY",
        "per_request",
    ) #Estratégia de rotação (per_request | per_session | per_domain)
    SCRAPER_USE_FAKE_USERAGENT: bool = os.getenv(
        "SCRAPER_USE_FAKE_USERAGENT",
        "true",
    ).lower() in {"1", "True", "true", "yes", "on"} #Controla uso do fake-useragent dinâmico
    SCRAPER_FAKE_UA_CACHE_TTL_SECONDS: int = int(
        os.getenv("SCRAPER_FAKE_UA_CACHE_TTL_SECONDS", "86400")
    ) #TTL do cache local do fake-useragent (segundos)
    SCRAPER_FAKE_UA_CACHE_MAX_SIZE: int = int(
        os.getenv("SCRAPER_FAKE_UA_CACHE_MAX_SIZE", "32")
    )  #Itens máximos do cache de UA dinâmicos
    SCRAPER_FAKE_UA_FETCH_TIMEOUT_SECONDS: float = float(
        os.getenv("SCRAPER_FAKE_UA_FETCH_TIMEOUT_SECONDS", "2.0")
    )  #Tempo limite para obter UA do fake-useragent

    SCRAPER_HEADERS_ACCEPT: str = os.getenv(
        "SCRAPER_HEADERS_ACCEPT",
        "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp," "image/apng,*/*;q=0.8",
    )  #Valor do header Accept padrão
    SCRAPER_HEADERS_ACCEPT_LANGUAGE: str = os.getenv(
        "SCRAPER_HEADERS_ACCEPT_LANGUAGE",
        "pt-BR,pt;q=0.9,en-US;q=0.8,en;q=0.7",
    )  #Valor do header Accept-Language padrão
    SCRAPER_HEADERS_CONNECTION: str = os.getenv(
        "SCRAPER_HEADERS_CONNECTION",
        "keep-alive",
    )  #Valor do header Connection padrão
    SCRAPER_HEADERS_REFERER_TEMPLATE: str | None = os.getenv(
        "SCRAPER_HEADERS_REFERER_TEMPLATE",
        None,
    )  #Template opcional para construir Referer dinâmico

    SCRAPER_LOG_4XX_BODY: bool = os.getenv("SCRAPER_LOG_4XX_BODY", "false").lower() in {
        "1",
        "True",
        "true",
        "yes",
        "on",
    } #Controla logging do corpo em respostas 4xx
    SCRAPER_LOG_4XX_MAX_BYTES: int = int(
        os.getenv("SCRAPER_LOG_4XX_MAX_BYTES", "512")
    ) #Limite de bytes registrados do corpo 4xx

    SCRAPER_USE_CLOUDSCRAPER_FALLBACK: bool = os.getenv(
        "SCRAPER_USE_CLOUDSCRAPER_FALLBACK", 
        "true",
    ).lower() in {"1", "True", "true", "yes", "on"}
    SCRAPER_CLOUDSCRAPER_DOMAINS: Tuple[str, ...] = tuple(
        sorted(
            {
                domain.strip().lower()
                for domain in os.getenv("SCRAPER_CLOUDSCRAPER_DOMAINS", "").split(",")
                if domain.strip()
            }
        )
    ) #Domínios com fallback obrigatório
    SCRAPER_CLOUDSCRAPER_TIMEOUT_SECONDS: float = float(
        os.getenv("SCRAPER_CLOUDSCRAPER_TIMEOUT_SECONDS", "10.0")
    ) #Timeout para chamadas sincronas do cloudscraper

#Instância única de settings para a aplicação
settings = Settings()
