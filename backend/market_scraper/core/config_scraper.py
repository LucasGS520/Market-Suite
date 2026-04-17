""" Define parâmetros essenciais do serviço MarketScraper.

O objetivo deste módulo é expor somente variáveis de configuração
necessárias para operar o pipeline determinístico. Todas as entradas
estão alinhadas com o comportamento documentado e evitam toggles
complexos que geravam ramificações de execução difíceis de auditar.
"""

from __future__ import annotations

import os
from typing import Dict, Tuple

from shared.core.config_base import ConfigBase


__all__ = ["Settings", "settings"]

class Settings(ConfigBase):
    """ Organiza configurações essenciais expostas ao MarketScraper """

    # --- Rate limiter por histórico ---
    SCRAPER_RATE_LIMITER_BLOCK_ENABLED: bool = os.getenv(
        "SCRAPER_RATE_LIMITER_BLOCK_ENABLED", "False"
    ).lower() in {"1", "true", "on", "yes"}
    # Padrão False (observação): cooldown registra log sem bloquear a coleta.
    # Defina True em produção para bloquear domínios em cooldown severo.

    # --- Política de robots.txt ---
    SCRAPER_ROBOTS_MODE: str = os.getenv("SCRAPER_ROBOTS_MODE", "audit").lower()
    # Padrão "audit": robots.txt é sinal observável; pipeline prossegue e
    # context.data["robots_disallowed"] é marcado para telemetria.
    # Defina "block" em produção para interromper a coleta em URLs disallowed.

    # --- Orçamentos de aquisição (HTTP e browser) ---
    # Dois orçamentos independentes substituem o timeout único por etapa para o FetchHTMLStep,
    # eliminando a variabilidade causada por microetapas e interrupções prematuras.
    SCRAPER_HTTP_BUDGET_SECONDS: float = float(
        os.getenv("SCRAPER_HTTP_BUDGET_SECONDS", "10.0")
    )  # Orçamento para curl_cffi, incluindo retries configurados
    SCRAPER_BROWSER_BUDGET_SECONDS: float = float(
        os.getenv("SCRAPER_BROWSER_BUDGET_SECONDS", "25.0")
    )  # Orçamento para fallback Playwright (navegação + renderização)

    # --- Cache e execução do pipeline ---
    #Mantemos apenas controles numéricos necessários para previsibilidade.
    SCRAPER_CACHE_TTL_SECONDS: int = int(
        os.getenv("SCRAPER_CACHE_TTL_SECONDS", "3600")
    ) #TTL padrão por URL (segundos)
    SCRAPER_CACHE_MAX_ENTRIES: int = int(
        os.getenv("SCRAPER_CACHE_MAX_ENTRIES", "5000")
    ) #Limites de itens armazenados em memória

    SCRAPER_STEP_TIMEOUT_SECONDS: float = float(
        os.getenv("SCRAPER_STEP_TIMEOUT_SECONDS", "15.0")
    )  # Timeout para etapas de parsing; FetchHTMLStep usa os orçamentos acima
    SCRAPER_PIPELINE_TIMEOUT_SECONDS: float = float(
        os.getenv("SCRAPER_PIPELINE_TIMEOUT_SECONDS", "50.0")
    )  # Segurança global: HTTP_BUDGET + BROWSER_BUDGET + overhead de parsing

    SCRAPER_SINGLEFLIGHT_LOCK_TTL: float = float(
        os.getenv("SCRAPER_SINGLEFLIGHT_LOCK_TTL", "15.0")
    )  #TTL dos locks de singleflight
    SCRAPER_SINGLEFLIGHT_MAX_ENTRIES: int = int(
        os.getenv("SCRAPER_SINGLEFLIGHT_MAX_ENTRIES", "2000")
    )  #Limite de entradas em memória do singleflight
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
    SCRAPER_HEADERS_DEFAULT_COOKIES: str = os.getenv(
        "SCRAPER_HEADERS_DEFAULT_COOKIES",
        "",
    ) #Cookies opcionais enviados por padrão
    SCRAPER_HEADERS_ADDITIONAL: str = os.getenv(
        "SCRAPER_HEADERS_ADDITIONAL",
        "",
    ) #Headers adicionais enviados além do conjunto mínimo

    # --- Observabilidade ---
    SCRAPER_LOG_4XX_BODY: bool = os.getenv("SCRAPER_LOG_4XX_BODY", "True").lower() in {
        "1",
        "true",
        "on",
        "yes",
    } #Controla logging do corpo em respostas 4xx
    SCRAPER_LOG_4XX_MAX_BYTES: int = int(
        os.getenv("SCRAPER_LOG_4XX_MAX_BYTES", "1024")
    ) #Limite de bytes registrados em logs de 4xx

    SCRAPER_HTTP_FOLLOW_REDIRECTS: bool = os.getenv(
        "SCRAPER_HTTP_FOLLOW_REDIRECTS",
        "true",
    ).lower() in {"1", "true", "on", "yes"} #Controla comportamento de redirecionamentos
    SCRAPER_HTTP_DOMAIN_TIMEOUTS: str = os.getenv(
        "SCRAPER_HTTP_DOMAIN_TIMEOUTS",
        "",
    ) #Permite sobreescrever timeout total por domínio

    def get_default_cookies(self) -> Dict[str, str]:
        """ Retorna cookies básicos enviados em todas as requisições 
        
        O formato esperado é uma lista delimitada por ``||`` em que cada
        item segue ``chave=valor``. Entradas inválidas são ignoradas para
        manter tolerância com configurações dinâmicas.
        """
        return self._parse_key_value_pairs(self.SCRAPER_HEADERS_DEFAULT_COOKIES)

    def get_additional_headers(self) -> Dict[str, str]:
        """ Retorna headers complementares configurados para o scraper
        
        O método aplica a mesma regra de parsing dos cookies, permitindo
        sobrescrever seletivamente headers utilizados pelo pipeline
        """
        return self._parse_key_value_pairs(self.SCRAPER_HEADERS_ADDITIONAL)
    
    def resolve_domain_timeout(self, domain: str | None, fallback: float) -> float:
        """ Devolve timeout específico do domínio quando configurado 
        
        O formato aceito também utiliza ``||`` como separador e valores
        em segundos. Nomes de domínio são normalizados para minúsculas
        """
        if not domain:
            return fallback
        
        normalized = domain.lower()
        mapping = self._parse_domain_timeouts(self.SCRAPER_HTTP_DOMAIN_TIMEOUTS)
        return mapping.get(normalized, fallback)
    
    @staticmethod
    def _parse_key_value_pairs(raw: str) -> Dict[str, str]:
        """ Converte string delimitada em dicionário ``{chave: valor}`` 
        
        Entradas sem ``=`` ou com chave vazia são descartadas para evitar
        propagação de valores inconsistentes para o cliente HTTP.
        """
        if not raw:
            return {}
        
        parsed: Dict[str, str] = {}
        for item in raw.split("||"):
            chunk = item.strip()
            if not chunk or "=" not in chunk:
                continue

            key, _, value = chunk.partition("=")
            key = key.strip()
            if not key:
                continue
            parsed[key] = value.strip()

        return parsed
    
    @staticmethod
    def _parse_domain_timeouts(raw: str) -> Dict[str, float]:
        """ Converte configuração de timeout por domínio em ``dict`` 
        
        Valores inválidos são ignorados silenciosamente para manter o
        pipeline resiliente a erros de configuração. Os valores retornados
        estão sempre em segundos.
        """
        if not raw:
            return {}
        
        parsed: Dict[str, float] = {}
        for item in raw.split("||"):
            chunk = item.strip()
            if not chunk or "=" not in chunk:
                continue

            domain, _, raw_value = chunk.partition("=")
            domain = domain.strip().lower()
            if not domain:
                continue

            try:
                parsed[domain] = float(raw_value.strip())
            except ValueError:
                continue

        return parsed

#Instância única de settings para a aplicação
settings = Settings()
