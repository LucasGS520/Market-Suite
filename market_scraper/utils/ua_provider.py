""" Fornece User-Agents realistas com rotação controlada

O módulo combina um pool estático curado com fallback via ``fake_useragent``
para reduzir bloqueios causados por cabeçalhos pouco realistas. A rotação
é configurável por requisição, sessão ou domínio, alinhada às opções
expostas em ``config_scraper``. Como o fake-useragent realiza operações
síncronas, encapsulamos a chamada em executor dedicado com timeout curto.
"""

from __future__ import annotations

import threading
from concurrent.futures import ThreadPoolExecutor, TimeoutError
from typing import Dict, Optional
from urllib.parse import urlparse

import structlog
from cachetools import TTLCache
from fake_useragent import FakeUserAgent, FakeUserAgentError

from market_scraper.core.config_scraper import settings


__all__ = ["get_user_agent", "reset_provider_state"]

logger = structlog.get_logger(__name__)

#Utilizamos executor único para evitar múltiplos downloads do fake-useragent
_FAKE_UA_EXECUTOR = ThreadPoolExecutor(max_workers=1)
_FAKE_UA_LOCK = threading.Lock()
_FAKE_UA_CLIENT: FakeUserAgent | None = None

#Estruturas de rotação (inicializadas abaixo)
_STATIC_POOL: list[str] = []
_STATIC_POOL_INDEX = 0
_STATIC_POOL_LOCK = threading.Lock()

_SESSION_CACHE: Dict[str, str] = {}
_SESSION_CACHE_LOCK = threading.Lock()

_DOMAIN_CACHE: Dict[str, str] = {}
_DOMAIN_CACHE_LOCK = threading.Lock()

_FAKE_UA_CACHE: TTLCache[str, str]

def _build_ttl_cache() -> TTLCache[str, str]:
    """ Cria cache TTL de User-Agents dinâmicos usando configurações atuais """
    return TTLCache(
        maxsize=settings.SCRAPER_FAKE_UA_CACHE_MAX_SIZE,
        ttl=settings.SCRAPER_FAKE_UA_CACHE_TTL_SECONDS,
    )

_FAKE_UA_CACHE = _build_ttl_cache()

def reset_provider_state() -> None:
    """ Reinicia caches e contadores (destinado apenas a testes automatizados) """
    global _STATIC_POOL, _STATIC_POOL_INDEX, _FAKE_UA_CACHE
    global _SESSION_CACHE, _DOMAIN_CACHE

    with _STATIC_POOL_LOCK:
        # Reconstruímos o pool a partir das configurações atuais
        _STATIC_POOL = list(settings.SCRAPER_USER_AGENT_STATIC_POOL)
        _STATIC_POOL_INDEX = 0

    with _SESSION_CACHE_LOCK:
        _SESSION_CACHE = {}

    with _DOMAIN_CACHE_LOCK:
        _DOMAIN_CACHE = {}

    # Recriamos o cache TTL para respeitar novos limites configurados
    _FAKE_UA_CACHE = _build_ttl_cache()

#Executamos reset ao importar para alinhar estado inicial ao settings
reset_provider_state()

def get_user_agent(url_or_domain: str, *, session_id: str | None = None) -> str:
    """ Retorna User-Agent respeitando a estratégia definida no settings
    
    Args:
        url_or_domain: URL completa ou domínio utilizado para scoping.
        session_id: Identificador opcional de sessão, usando quando a
            estratégia configurada exige afinidade por sessão.

    Returns:
        User-Agent escolhido conforme prioridade: pool estático -> cache
        fake-useragent -> valor padrão configurado
    """
    strategy = settings.SCRAPER_USER_AGENT_ROTATION_STRATEGY.lower()
    domain = _extract_domain(url_or_domain)

    if strategy == "per_session":
        key = session_id or "__default__"
        return _get_session_user_agent(key)
    
    if strategy == "per_domain" and domain:
        return _get_domain_user_agent(domain)

    #Fallback para rotação por requisição ou domínio inválido
    return _next_user_agent()

def _get_session_user_agent(key: str) -> str:
    """ Retorna UA fixo por sessão criando entrada quando necessário """
    with _SESSION_CACHE_LOCK:
        if key in _SESSION_CACHE:
            return _SESSION_CACHE[key]
        
        ua = _next_user_agent()
        _SESSION_CACHE[key] = ua
        return ua
    
def _get_domain_user_agent(domain: str) -> str:
    """ Retorna UA fixo por domínio normalizado criando entrada quando necessário """
    normalized = domain.lower()

    with _DOMAIN_CACHE_LOCK:
        if normalized in _DOMAIN_CACHE:
            return _DOMAIN_CACHE[normalized]
        
        ua = _next_user_agent()
        _DOMAIN_CACHE[normalized] = ua
        return ua
    
def _next_user_agent() -> str:
    """ Obtém próximo UA disponível priorizando o pool curado """
    ua = _next_from_static_pool()
    if ua:
        return ua
    
    ua = _get_fake_user_agent()
    if ua:
        return ua
    
    #Utilizamos valor padrão para evitar retorno vazio
    return settings.SCRAPER_USER_AGENT_DEFAULT

def _next_from_static_pool() -> Optional[str]:
    """ Faz round-robin no pool estático retornando próximo UA disponível """
    with _STATIC_POOL_LOCK:
        if not _STATIC_POOL:
            return None
        
        global _STATIC_POOL_INDEX
        ua = _STATIC_POOL[_STATIC_POOL_INDEX % len(_STATIC_POOL)]
        _STATIC_POOL_INDEX = (_STATIC_POOL_INDEX + 1) % len(_STATIC_POOL)
        return ua
    
def _get_fake_user_agent() -> Optional[str]:
    """ Busca UA dinâmico com cache e tratamento de falhas silencioso """
    cache_key = "default"
    try:
        return _FAKE_UA_CACHE[cache_key]
    except KeyError:
        pass

    try:
        ua = _fetch_fake_user_agent_with_timeout()
    except (RuntimeError, TimeoutError):
        logger.warning("fake_useragent_unavailable", strategy="ua_provider")
        return None
    
    if not ua:
        return None
    
    _FAKE_UA_CACHE[cache_key] = ua
    return ua

def _fetch_fake_user_agent_with_timeout() -> Optional[str]:
    """ Encapsula acesso ao fake-useragent com timeout configurável """
    
    def _load_random() -> Optional[str]:
        """ Carrega instância singleton do fake-useragent e retorna UA aleatório """
        global _FAKE_UA_CLIENT
        with _FAKE_UA_LOCK:
            if _FAKE_UA_CLIENT is None:
                #Inicialização tardia evita custo em import
                _FAKE_UA_CLIENT = FakeUserAgent()

            client = _FAKE_UA_CLIENT

        try:
            return client.random
        except FakeUserAgentError as exc:
            #Registramos erro para depuração futura sem interromper pipeline
            logger.warning("fake_useragent_error", error=str(exc))
            return None
        
    future = _FAKE_UA_EXECUTOR.submit(_load_random)
    return future.result(timeout=settings.SCRAPER_FAKE_UA_FETCH_TIMEOUT_SECONDS)

def _extract_domain(value: str | None) -> Optional[str]:
    """ Normaliza domínio a partir de URL ou string simples """
    if not value:
        return None
    
    parsed = urlparse(value)
    if parsed.hostname:
        return parsed.hostname
    
    #Tratamos entradas parciais mantendo robustez
    stripped = value.strip().split("/")[0]
    return stripped or None
