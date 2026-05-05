""" Define parâmetros essenciais do serviço MarketScraper.

O objetivo deste módulo é expor somente variáveis de configuração
necessárias para operar o pipeline determinístico. Todas as entradas
estão alinhadas com o comportamento documentado e evitam toggles
complexos que geravam ramificações de execução difíceis de auditar.
"""

from __future__ import annotations

import os
from typing import Dict

from pydantic import model_validator
from shared.core.config_base import ConfigBase, PYTEST_RUNNING


#Domínios que exigem proxy em staging/production para evitar bloqueio anti-bot.
#Checagem via substring case-insensitive do hostname.
_PROXY_REQUIRED_DOMAIN_FRAGMENTS: frozenset[str] = frozenset({
    "mercadolivre",
    "mercadolibre",
})

__all__ = ["Settings", "settings"]

class Settings(ConfigBase):
    """ Organiza configurações essenciais expostas ao MarketScraper """

    # --- Ambiente de execução ---
    SCRAPER_ENV: str = os.getenv("SCRAPER_ENV", "local").lower()
    #"local" (padrão): proxy opcional, sem fail-fast de configuração.
    #"staging" ou "production": proxy obrigatório para domínios sensíveis (ex.: Mercado Livre).

    # --- Rate limiter por histórico ---
    SCRAPER_RATE_LIMITER_BLOCK_ENABLED: bool = os.getenv(
        "SCRAPER_RATE_LIMITER_BLOCK_ENABLED", "False"
    ).lower() in {"1", "true", "on", "yes"}
    #Padrão False (observação): cooldown registra log sem bloquear a coleta.
    #Defina True em produção para bloquear domínios em cooldown severo.

    # --- Política de robots.txt ---
    SCRAPER_ROBOTS_MODE: str = os.getenv("SCRAPER_ROBOTS_MODE", "warn").lower()
    #"warn" (padrão local/dev): verifica robots.txt, loga se disallowed, prossegue sem bloquear.
    #"strict" (staging/production): bloqueia imediatamente com 403 se can_fetch=false.
    #"ignore": não verifica robots.txt; sem interferência na execução.

    SCRAPER_ROBOTS_CACHE_TTL: int = int(os.getenv("SCRAPER_ROBOTS_CACHE_TTL", "3600"))
    #TTL do cache Redis para robots.txt (segundos). Padrão 1h (3600s).
    #Reduza para domínios com políticas voláteis; aumente para reduzir requisições de rede.

    # --- Orçamentos de aquisição (HTTP e browser) ---
    #Dois orçamentos independentes substituem o timeout único de aquisição, eliminando a variabilidade causada por microetapas e interrupções prematuras.
    SCRAPER_HTTP_BUDGET_SECONDS: float = float(
        os.getenv("SCRAPER_HTTP_BUDGET_SECONDS", "10.0")
    ) #Orçamento para curl_cffi, incluindo retries configurados
    SCRAPER_BROWSER_BUDGET_SECONDS: float = float(
        os.getenv("SCRAPER_BROWSER_BUDGET_SECONDS", "20.0")
    ) #Orçamento para fallback Playwright (navegação + renderização); compatível com endpoint síncrono ≤35s
    SCRAPER_BROWSER_NAVIGATION_TIMEOUT_SECONDS: float = float(
        os.getenv("SCRAPER_BROWSER_NAVIGATION_TIMEOUT_SECONDS", "10.0")
    ) #Timeout de navegação por tentativa reduzido; deve ser < SCRAPER_BROWSER_BUDGET_SECONDS
    SCRAPER_BROWSER_MAX_RETRIES: int = int(
        os.getenv("SCRAPER_BROWSER_MAX_RETRIES", "0")
    ) #Retries extras no browser (0 = tentativa única). Retries > 0 podem gerar browser_handler_orphan quando o budget externo vence durante uma segunda tentativa do Crawlee.
    SCRAPER_BROWSER_EARLY_EXIT_ENABLED: bool = os.getenv(
        "SCRAPER_BROWSER_EARLY_EXIT_ENABLED", "True"
    ).lower() in {"1", "true", "on", "yes"}
    #Encerra navegação assim que HTML com sinais de produto for obtido
    SCRAPER_BROWSER_EARLY_EXIT_MIN_HTML_BYTES: int = int(
        os.getenv("SCRAPER_BROWSER_EARLY_EXIT_MIN_HTML_BYTES", "1024")
    ) #Tamanho mínimo (bytes) para considerar HTML útil no early-exit
    SCRAPER_BROWSER_CONCURRENCY: int = int(
        os.getenv("SCRAPER_BROWSER_CONCURRENCY", "5")
    ) #Máximo de instâncias Playwright simultâneas; usar 1 em staging para debug previsível

    # --- Observabilidade aprimorada ---
    SCRAPER_TELEMETRY_VERBOSE: bool = os.getenv(
        "SCRAPER_TELEMETRY_VERBOSE", "false"
    ).lower() in {"1", "true", "on", "yes"}
    #Padrão False. True = loga session_id, attempt_number e timestamps em cada fetch do browser.
    #Ativar em staging/debug para rastrear race conditions e lifecycle de sessão.

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
    ) #Timeout para etapas de parsing; coleta usa os orçamentos acima
    SCRAPER_PIPELINE_TIMEOUT_SECONDS: float = float(
        os.getenv("SCRAPER_PIPELINE_TIMEOUT_SECONDS", "35.0")
    ) #Segurança global: endpoint síncrono ≤35s; deve ser >= HTTP_BUDGET + BROWSER_BUDGET + 5s (validado no startup)

    SCRAPER_SINGLEFLIGHT_LOCK_TTL: float = float(
        os.getenv("SCRAPER_SINGLEFLIGHT_LOCK_TTL", "15.0")
    )  #TTL dos locks de singleflight
    SCRAPER_SINGLEFLIGHT_MAX_ENTRIES: int = int(
        os.getenv("SCRAPER_SINGLEFLIGHT_MAX_ENTRIES", "2000")
    )  #Limite de entradas em memória do singleflight
    SCRAPER_PRICE_TOLERANCE: float = float(
        os.getenv("SCRAPER_PRICE_TOLERANCE", "0.0")
    )  #Tolerância percentual na comparação de preços

    # --- Configurações HTTP (cliente httpx — robots.py + http_utils.py) ---
    SCRAPER_HTTP_TIMEOUT_CONNECT: float = float(
        os.getenv("SCRAPER_HTTP_TIMEOUT_CONNECT", "3.0")
    ) #Tempo máximo para estabelecer conexão (httpx — robots.py)
    SCRAPER_HTTP_TIMEOUT_READ: float = float(
        os.getenv("SCRAPER_HTTP_TIMEOUT_READ", "3.0")
    ) #Tempo limite de leitura por requisição (httpx — robots.py)
    SCRAPER_HTTP_TIMEOUT_WRITE: float = float(
        os.getenv("SCRAPER_HTTP_TIMEOUT_WRITE", "3.0")
    ) #Tempo limite de escrita/envio (httpx — robots.py)
    SCRAPER_HTTP_TIMEOUT_POOL: float = float(
        os.getenv("SCRAPER_HTTP_TIMEOUT_POOL", "3.0")
    ) #Tempo máximo aguardando conexão no pool (httpx — robots.py)

    SCRAPER_HTTP_RETRIES: int = int(
        os.getenv("SCRAPER_HTTP_RETRIES", "2")
    ) #Tentativas extras para downloads HTTP (max_request_retries no HttpCrawler)
    SCRAPER_HTTP_RETRY_BACKOFF_BASE: float = float(
        os.getenv("SCRAPER_HTTP_RETRY_BACKOFF_BASE", "0.5")
    ) #Base do backoff exponencial aplicado aos retries (httpx — robots.py)

    SCRAPER_HTTP_MAX_REDIRECTS: int = int(
        os.getenv("SCRAPER_HTTP_MAX_REDIRECTS", "3")
    ) #Limite de redirecionamentos seguidos (max_redirects no CurlImpersonateHttpClient)
    SCRAPER_HTTP_MAX_CONNECTIONS: int = int(
        os.getenv("SCRAPER_HTTP_MAX_CONNECTIONS", "10")
    ) #Conexões simultâneas no client HTTP (httpx — robots.py)
    SCRAPER_HTTP_MAX_KEEPALIVE: int = int(
        os.getenv("SCRAPER_HTTP_MAX_KEEPALIVE", "5")
    ) #Conexões preservadas em keep-alive (httpx — robots.py)
    SCRAPER_HTTP_MAX_CONTENT_LENGTH: int = int(
        os.getenv("SCRAPER_HTTP_MAX_CONTENT_LENGTH", "2000000")
    ) #Tamanho máximo permitido para payloads (truncagem em http_collector)

    # --- DNS (http_utils.py) ---
    SCRAPER_DNS_TIMEOUT: float = float(
        os.getenv("SCRAPER_DNS_TIMEOUT", "2.0")
    ) #Tempo limite das resoluções DNS
    SCRAPER_DNS_CACHE_TTL: float = float(
        os.getenv("SCRAPER_DNS_CACHE_TTL", "120.0")
    ) #Tempo em segundos que respostas DNS permanecem em cache

    # --- Identidade operacional (proxy + sessão) ---
    SCRAPER_PROXY_URLS: str = os.getenv("SCRAPER_PROXY_URLS", "")
    #Lista de URLs de proxy separada por "||". Vazio = sem proxy (coleta sem rotação de IP).
    #Exemplo: "http://user:pass@proxy1:8080||http://user:pass@proxy2:8080"
    SCRAPER_SESSION_POOL_MAX_SIZE: int = int(
        os.getenv("SCRAPER_SESSION_POOL_MAX_SIZE", "20")
    ) #Número máximo de sessões no pool (padrão Crawlee = 1000; reduzido para scraping direcionado)

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

    SCRAPER_DEBUG_HTML_DUMP: bool = os.getenv(
        "SCRAPER_DEBUG_HTML_DUMP", "false"
    ).lower() in {"1", "true", "on", "yes"}
    #Padrão False: sem efeito em produção.
    #Defina True para registrar amostra do HTML coletado em cada extraction_empty.
    SCRAPER_DEBUG_HTML_MAX_BYTES: int = int(
        os.getenv("SCRAPER_DEBUG_HTML_MAX_BYTES", "8192")
    ) #Tamanho máximo da amostra de HTML registrada no dump (bytes)

    # --- Opções de runtime do browser (Playwright) ---
    SCRAPER_BROWSER_DISABLE_DEV_SHM: bool = os.getenv(
        "PLAYWRIGHT_DISABLE_DEV_SHM", "true"
    ).lower() in {"1", "true", "on", "yes"}
    #Passa --disable-dev-shm-usage ao Chromium. Necessário em containers com /dev/shm pequeno.
    #Padrão True (seguro em VPS/staging). Desabilite apenas em dev-local com /dev/shm grande.
    SCRAPER_BROWSER_DEBUG_SCREENSHOTS: bool = os.getenv(
        "PLAYWRIGHT_DEBUG_SCREENSHOTS", "false"
    ).lower() in {"1", "true", "on", "yes"}
    #Salva screenshot em tests/debug/ quando anti-bot é detectado. Padrão False.
    #Ative apenas localmente para diagnóstico — não usar em staging/produção.

    SCRAPER_HTTP_FOLLOW_REDIRECTS: bool = os.getenv(
        "SCRAPER_HTTP_FOLLOW_REDIRECTS",
        "true",
    ).lower() in {"1", "true", "on", "yes"} #Controla comportamento de redirecionamentos
    SCRAPER_HTTP_DOMAIN_TIMEOUTS: str = os.getenv(
        "SCRAPER_HTTP_DOMAIN_TIMEOUTS",
        "",
    ) #Permite sobreescrever timeout total por domínio

    def proxy_required_for(self, domain: str) -> bool:
        """ True se o domínio exige proxy no ambiente atual e SCRAPER_PROXY_URLS está vazio.

        Em "local" o proxy é opcional — retorna sempre False.
        Em "staging" e "production", domínios da lista _PROXY_REQUIRED_DOMAIN_FRAGMENTS
        exigem proxy ativo; sem ele a coleta seria tentada com identidade única,
        o que resulta em bloqueio anti-bot previsível.
        """
        if self.SCRAPER_ENV not in {"staging", "production"}:
            return False
        if self.SCRAPER_PROXY_URLS.strip():
            return False
        domain_lower = domain.lower()
        return any(frag in domain_lower for frag in _PROXY_REQUIRED_DOMAIN_FRAGMENTS)

    @model_validator(mode="after")
    def _validate_timeout_hierarchy(self) -> "Settings":
        if PYTEST_RUNNING:
            return self
        # pipeline deve acomodar HTTP + browser + overhead mínimo de 5s de parsing
        min_pipeline = self.SCRAPER_HTTP_BUDGET_SECONDS + self.SCRAPER_BROWSER_BUDGET_SECONDS + 5.0
        if self.SCRAPER_PIPELINE_TIMEOUT_SECONDS < min_pipeline:
            raise ValueError(
                f"SCRAPER_PIPELINE_TIMEOUT_SECONDS ({self.SCRAPER_PIPELINE_TIMEOUT_SECONDS}s) "
                f"deve ser >= HTTP_BUDGET + BROWSER_BUDGET + 5s = {min_pipeline}s. "
                "Ajuste o .env ou aumente SCRAPER_PIPELINE_TIMEOUT_SECONDS."
            )
        if self.SCRAPER_BROWSER_NAVIGATION_TIMEOUT_SECONDS >= self.SCRAPER_BROWSER_BUDGET_SECONDS:
            raise ValueError(
                f"SCRAPER_BROWSER_NAVIGATION_TIMEOUT_SECONDS ({self.SCRAPER_BROWSER_NAVIGATION_TIMEOUT_SECONDS}s) "
                f"deve ser < SCRAPER_BROWSER_BUDGET_SECONDS ({self.SCRAPER_BROWSER_BUDGET_SECONDS}s)."
            )
        return self

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
