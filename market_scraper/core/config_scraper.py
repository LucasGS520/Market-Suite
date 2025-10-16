""" Define parâmetros essenciais do serviço MarketScraper.

O objetivo deste módulo é expor somente variáveis de configuração
necessárias para operar o pipeline determinístico. Todas as entradas
estão alinhadas com o comportamento documentado e evitam toggles
complexos que geravam ramificações de execução difíceis de auditar.
"""

from __future__ import annotations

import os
from typing import Tuple

from shared.core.config_base import ConfigBase


__all__ = ["Settings", "settings"]

class Settings(ConfigBase):
    """ Organiza configurações essenciais expostas ao MarketScraper """

    # --- Cache e execução do pipeline ---
    #Mantemos apenas controles numéricos necessários para previsibilidade.
    SCRAPER_CACHE_TTL_SECONDS: int = int(
        os.getenv("SCRAPER_CACHE_TTL_SECONDS", "3600")
    ) #TTL padrão por URL (segundos)
    SCRAPER_CACHE_MAX_ENTRIES: int = int(
        os.getenv("SCRAPER_CACHE_MAX_ENTRIES", "5000")
    ) #Limites de itens armazenados em memória

    SCRAPER_STEP_TIMEOUT_SECONDS: float = float(
        os.getenv("SCRAPER_STEP_TIMEOUT_SECONDS", "8.0")
    ) #Tempo máximo por etapa do pipeline
    SCRAPER_PIPELINE_TIMEOUT_SECONDS: float = float(
        os.getenv("SCRAPER_PIPELINE_TIMEOUT_SECONDS", "20.0")
    ) #Tempo máximo total do pipeline

    SCRAPER_SINGLEFLIGHT_LOCK_TTL: float = float(
        os.getenv("SCRAPER_SINGLEFLIGHT_LOCK_TTL", "15.0")
    )  #TTL dos locks de singleflight
    SCRAPER_PRICE_TOLERANCE: float = float(
        os.getenv("SCRAPER_PRICE_TOLERANCE", "0.0")
    )  #Tolerância percentual na comparação de preços

    # --- Configurações HTTP ---
    SCRAPER_HTTP_TIMEOUT_CONNECT: float = float(
        os.getenv("SCRAPER_HTTP_TIMEOUT_CONNECT", "3.0")
    ) #Tempo máximo para estabelecer conexão
    SCRAPER_HTTP_TIMEOUT_READ: float = float(
        os.getenv("SCRAPER_HTTP_TIMEOUT_READ", "3.0")
    ) #Tempo limite de leitura por requisição
    SCRAPER_HTTP_TIMEOUT_WRITE: float = float(
        os.getenv("SCRAPER_HTTP_TIMEOUT_WRITE", "3.0")
    ) #Tempo limite de escrita/envio
    SCRAPER_HTTP_TIMEOUT_POOL: float = float(
        os.getenv("SCRAPER_HTTP_TIMEOUT_POOL", "3.0")
    ) #Tempo máximo aguardando conexão no pool

    SCRAPER_HTTP_RETRIES: int = int(
        os.getenv("SCRAPER_HTTP_RETRIES", "2")
    ) #Tentativas extras para downloads HTTP
    SCRAPER_HTTP_RETRY_BACKOFF_BASE: float = float(
        os.getenv("SCRAPER_HTTP_RETRY_BACKOFF_BASE", "0.5")
    ) #Base do backoff exponencial aplicado aos retries
    
    SCRAPER_HTTP_MAX_REDIRECTS: int = int(
        os.getenv("SCRAPER_HTTP_MAX_REDIRECTS", "3")
    ) #Limite de redirecionamentos seguidos
    SCRAPER_HTTP_MAX_CONNECTIONS: int = int(
        os.getenv("SCRAPER_HTTP_MAX_CONNECTIONS", "10")
    ) #Conexões simultâneas no client HTTP
    SCRAPER_HTTP_MAX_KEEPALIVE: int = int(
        os.getenv("SCRAPER_HTTP_MAX_KEEPALIVE", "5")
    ) #Conexões preservadas em keep-alive
    SCRAPER_HTTP_MAX_CONTENT_LENGTH: int = int(
        os.getenv("SCRAPER_HTTP_MAX_CONTENT_LENGTH", "2000000")
    ) #Tamanho máximo permitido para payloads

    SCRAPER_DNS_TIMEOUT: float = float(
        os.getenv("SCRAPER_DNS_TIMEOUT", "2.0")
    ) #Tempo limite das resoluções DNS
    SCRAPER_DNS_CACHE_TTL: float = float(
        os.getenv("SCRAPER_DNS_CACHE_TTL", "120.0")
    ) #Tempo em segundos que respostas DNS permanecem em cache

    # --- Identidade HTTP ---
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

    SCRAPER_USER_AGENT_POOL: Tuple[str, ...] = tuple(
        ua.strip()
        for ua in os.getenv("SCRAPER_USER_AGENT_POOL", "||".join(_DEFAULT_UA_POOL)).split("||")
        if ua.strip()
    ) #Pool estático curado utilizado no round-robin
    SCRAPER_DEFAULT_USER_AGENT: str = os.getenv(
        "SCRAPER_DEFAULT_USER_AGENT",
        SCRAPER_USER_AGENT_POOL[0] if SCRAPER_USER_AGENT_POOL else _DEFAULT_UA_POOL[0],
    ) #Valor padrão utilizado quando o pool estiver vazio

    SCRAPER_HEADERS_ACCEPT: str = os.getenv(
        "SCRAPER_HEADERS_ACCEPT",
        "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
    )  #Header Accept coerente com navegadores modernos
    SCRAPER_HEADERS_ACCEPT_LANGUAGE: str = os.getenv(
        "SCRAPER_HEADERS_ACCEPT_LANGUAGE",
        "pt-BR,pt;q=0.9,en-US;q=0.8,en;q=0.7",
    )  #Header Accept-Language adotado pelo scraper
    SCRAPER_HEADERS_CONNECTION: str = os.getenv(
        "SCRAPER_HEADERS_CONNECTION",
        "keep-alive",
    )  #Header Connection padronizado
    SCRAPER_HEADERS_CACHE_CONTROL: str = os.getenv(
        "SCRAPER_HEADERS_CACHE_CONTROL",
        "max-age=0",
    )  #Header Cache-Control enviado por padrão
    SCRAPER_HEADERS_ACCEPT_ENCODING: str = os.getenv(
        "SCRAPER_HEADERS_ACCEPT_ENCODING",
        "gzip, deflate, br",
    )  #Header Accept-Encoding simples para conteúdo compactado
    SCRAPER_HEADERS_REFERER_TEMPLATE: str | None = os.getenv(
        "SCRAPER_HEADERS_REFERER_TEMPLATE",
        None,
    )  #Template opcional para construir Referer dinâmico

    # --- Observabilidade ---
    SCRAPER_LOG_4XX_BODY: bool = os.getenv("SCRAPER_LOG_4XX_BODY", "false").lower() in {
        "1",
        "true",
        "on",
        "yes",
    } #Controla logging do corpo em respostas 4xx
    SCRAPER_LOG_4XX_MAX_BYTES: int = int(
        os.getenv("SCRAPER_LOG_4XX_MAX_BYTES", "512")
    ) #Limite de bytes registrados em logs de 4xx

#Instância única de settings para a aplicação
settings = Settings()
