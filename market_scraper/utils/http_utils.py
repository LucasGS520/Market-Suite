""" Funções auxiliares para lidar com cabeçalhos HTTP e validações de host

Este módulo centraliza utilidades usadas por diferentes etapas do pipeline,
com destaque para validação de cabeçalhos como ``Retry-After`` e resolução
segura de hosts para prevenir SSRF.
"""

from __future__ import annotations

import ipaddress
import socket
import threading
import time
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Optional

try:
    import dns.exception
    import dns.resolver
except Exception: #Respeitamos ambientes sem dnspython e aplicamos fallback
    dns = None  #type: ignore

import structlog

from market_scraper.core.config_scraper import settings
from shared.metrics.metrics_scraper import (
    SCRAPER_DNS_BLOCKED_TOTAL,
    SCRAPER_DNS_RESOLVE_DURATION_SECONDS,
)


logger = structlog.get_logger(__name__)

#Cache de DNS simples potegido por lock para reduzir round-trips repetidos
_DNS_CACHE: dict[str, tuple[float, list[str]]] = {}
_DNS_CACHE_LOCK = threading.Lock()

def parse_retry_after(value: str) -> Optional[int]:
    """ Retorna o valor do cabeçalho ``Retry-After`` em segundos """
    if not value:
        return None

    value = value.strip()
    if value.isdigit():
        return int(value)

    try:
        dt = parsedate_to_datetime(value)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        diff = (dt - datetime.now(timezone.utc)).total_seconds()
        return max(0, int(diff))
    except Exception:
        return None

def extract_hostname(url: str) -> str:
    """ Retorna o nome do host de uma URL ou string vazia se inválida """
    from urllib.parse import urlparse

    try:
        return urlparse(str(url)).hostname or ""
    except Exception:
        return ""

class HostResolutionError(Exception):
    """ Indica falhas ao resolver ou validar o host informado """

def resolve_public_address(host: str) -> list[str]:
    """ Resolve o host e garante que todos os IPs pertencem a faixas públicas
    
    A resolução utiliza ``dnspython`` quando disponível para aplicar timeout
    determinístico; caso contrário, ``socket.getaddrinfo`` é executado em
    *threadpool* com o mesmo limite. Os resultados são cacheados por um TTL
    configurável para reduzir a latência em chamdas subsequentes.
    """
    if not host:
        raise HostResolutionError("Host vazio não resolvido")
    
    normalized_host = host.strip().lower().rstrip(".")
    if not normalized_host:
        raise HostResolutionError("Host vazio não resolvido")
    
    cache_ttl = max(0.0, float(getattr(settings, "SCRAPER_DNS_CACHE_TTL", 0)))
    now = time.monotonic()

    if cache_ttl:
        with _DNS_CACHE_LOCK:
            cached = _DNS_CACHE.get(normalized_host)
            if cached and cached[0] > now:
                SCRAPER_DNS_RESOLVE_DURATION_SECONDS.labels(outcome="cache").observe(0.0)
                return list(cached[1])
            
    start_time = time.perf_counter()
    try:
        addresses = _resolve_host_records(normalized_host)
    except HostResolutionError:
        duration = time.perf_counter() - start_time
        SCRAPER_DNS_RESOLVE_DURATION_SECONDS.labels(outcome="error").observe(duration)
        raise
    else:
        duration = time.perf_counter() - start_time
        SCRAPER_DNS_RESOLVE_DURATION_SECONDS.labels(outcome="resolved").observe(duration)

    if not addresses:
        raise HostResolutionError(f"Host sem endereços públicos: {normalized_host}")
    
    validated = _validate_public_addresses(normalized_host, addresses)

    if cache_ttl:
        expires_at = now + cache_ttl
        with _DNS_CACHE_LOCK:
            _DNS_CACHE[normalized_host] = (expires_at, validated)

    return validated

def resolve_public_addresses(host: str) -> list[str]:
        """ Alias plural que mantém compatibilidade com código legado """
        #Mantemos o comportamento único para evitar duplicar lógica de resolução DNS
        return resolve_public_address(host)

def _resolve_host_records(host: str) -> list[str]:
    """ Executa a resolução DNS considerando tempo limite configurável """
    timeout = float(getattr(settings, "SCRAPER_DNS_TIMEOUT", 2.0))
    try:
        if dns is not None:
            return _resolve_with_dnspython(host, timeout)
        return _resolve_with_socket(host, timeout)
    except HostResolutionError:
        raise
    except Exception as exc:
        logger.warning(
            "dns_resolution_failed",
            host=host,
            reason=str(exc),
        )
        raise HostResolutionError(f"Falha ao resolver host: {host}") from exc
  
def _resolve_with_dnspython(host: str, timeout: float) -> list[str]:
    """ Resolve registros A/AAAA utilizando dnspython com timeout explícito """
    resolver = dns.resolver.Resolver()
    resolver.lifetime = timeout
    resolver.timeout = timeout

    records: list[str] = []
    for record_type in ("A", "AAAA"):
        try:
            answers = resolver.resolve(host, record_type, lifetime=timeout)
        except (
            dns.resolver.NoAnswer,
            dns.resolver.NXDOMAIN,
            dns.resolver.NoNameservers,
        ): 
            continue
        except dns.exception.Timeout as exc:
            raise HostResolutionError(f"Timeout ao resolver host: {host}") from exc
        
        for answer in answers:
            records.append(answer.to_text())

    return records

def _resolve_with_socket(host: str, timeout: float) -> list[str]:
        """ Executa ``socket.getaddrinfo`` em thread separada respeitando timeout """
        from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeout

        def _worker() -> list[str]:
            try:
                addrinfo = socket.getaddrinfo(host, None, proto=socket.IPPROTO_TCP)
            except socket.gaierror as exc:
                raise HostResolutionError(f"Falha ao resolver host: {host}") from exc
            
            return [sockaddr[0] for *_rest, sockaddr in addrinfo if sockaddr]
        
        #Executor local garante liberação imediata sem reter threads ativas.
        with ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(_worker)
            try:
                return future.result(timeout=timeout)
            except FuturesTimeout as exc:
                future.cancel()
                raise HostResolutionError(f"Timeout ao resolver host: {host}") from exc

def _validate_public_addresses(host: str, addresses: list[str]) -> list[str]:
    """ Valida se todos os IPs são globais antes de liberar o host """
    validated: list[str] = []
    for ip_text in addresses:
        try:
            ip_obj = ipaddress.ip_address(ip_text)
        except ValueError as exc:
            raise HostResolutionError(f"Endereço IP inválido para {host}") from exc
        
        if not ip_obj.is_global:
            SCRAPER_DNS_BLOCKED_TOTAL.labels(reason="non_public").inc()
            logger.warning(
                "dns_resolution_blocked",
                host=host,
                ip=ip_text,
            )
            raise HostResolutionError(f"Endereço não público bloqueado: {ip_text}")
        
        validated.append(ip_text)

    return sorted(set(validated))


__all__ = [
    "HostResolutionError",
    "extract_hostname",
    "parse_retry_after",
    "resolve_public_address",
    "resolve_public_addresses",
]
