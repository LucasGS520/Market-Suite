""" Funções auxiliares para lidar com timeouts e validações de host

Este módulo centraliza utilidades usadas por diferentes etapas do pipeline,
com destaque para ``Retry-After``, timeouts aderentes às políticas globais
e resolução segura de hosts para prevenir SSRF.
"""

from __future__ import annotations

import ipaddress
import socket
import threading
import time
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeout
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Optional

import httpx
import structlog

from market_scraper.core.config_scraper import settings


logger = structlog.get_logger(__name__)

#Cache de DNS simples potegido por lock para reduzir round-trips repetidos e evitar condições de corrida entre threads do pipeline
_DNS_CACHE: dict[str, tuple[float, list[str]]] = {}
_DNS_CACHE_LOCK = threading.Lock()

def build_timeout(total_timeout: float) -> httpx.Timeout:
    """ Monta ``httpx.Timeout`` obedecendo limites específicos do scraper """
    #Ajustamos cada fase individual para respeitar valores máximos globais, evitando que cada chamada configure tempos exagerados
    return httpx.Timeout(
        total_timeout,
        connect=min(total_timeout, settings.SCRAPER_HTTP_TIMEOUT_CONNECT),
        read=min(total_timeout, settings.SCRAPER_HTTP_TIMEOUT_READ),
        write=min(total_timeout, settings.SCRAPER_HTTP_TIMEOUT_WRITE),
        pool=settings.SCRAPER_HTTP_TIMEOUT_POOL,
    )

def parse_retry_after(value: str | None) -> Optional[float]:
    """ Interpreta ``Retry-After`` em segundos, aceitando fracionários ou HTTP-date """
    if not value:
        return None

    normalized = value.strip()
    if not normalized:
        return None

    try:
        #Permite segundos fracionários
        seconds = float(normalized)
    except ValueError:
        try:
            dt = parsedate_to_datetime(normalized)
        except (TypeError, ValueError):
            return None
        
        if dt is None:
            return None

        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        
        diff = (dt - datetime.now(timezone.utc)).total_seconds()
        return max(0.0, diff)
    return max(0.0, seconds)

class HostResolutionError(Exception):
    """ Indica falhas ao resolver ou validar o host informado """

def resolve_public_address(host: str) -> list[str]:
    """ Resolve o host e garante que todos os IPs pertencem a faixas públicas
    
    A estratégia é determinística: executamos ``socket.getaddrinfo`` dentro de
    um *threadpool* respeitando ``SCRAPER_DNS_TIMEOUT``. Os resultados validados
    são cacheados por ``SCRAPER_DNS_CACHE_TTL`` segundos para mitigar 
    *latency spikes* sem acumular caminhos alternativos.
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
                return list(cached[1])
            
    try:
        addresses = _resolve_host_records(normalized_host)
    except HostResolutionError:
        raise

    if not addresses:
        raise HostResolutionError(f"Host sem endereços públicos: {normalized_host}")
    
    validated = _validate_public_addresses(normalized_host, addresses)

    if cache_ttl:
        expires_at = now + cache_ttl
        with _DNS_CACHE_LOCK:
            _DNS_CACHE[normalized_host] = (expires_at, validated)

    return validated

def _resolve_host_records(host: str) -> list[str]:
    """ Executa a resolução DNS considerando tempo limite configurável """
    timeout = float(getattr(settings, "SCRAPER_DNS_TIMEOUT", 2.0))
    try:
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

def _resolve_with_socket(host: str, timeout: float) -> list[str]:
    """ Executa ``socket.getaddrinfo`` em thread separada respeitando timeout """
    def _worker() -> list[str]:
        try:
            addrinfo = socket.getaddrinfo(host, None, proto=socket.IPPROTO_TCP)
        except socket.gaierror as exc:
            raise HostResolutionError(f"Falha ao resolver host: {host}") from exc
        
        return [sockaddr[0] for *_rest, sockaddr in addrinfo if sockaddr]
    
    #Executor local garante liberação imediata sem reter threads ativas
    with ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(_worker)
        try:
            return future.result(timeout=timeout)
        except FuturesTimeout as exc:
            future.cancel()
            raise HostResolutionError(f"Timeout ao resolver host: {host}") from exc

def _classify_non_public(
    ip_obj: ipaddress.IPv4Address | ipaddress.IPv6Address,
) -> str | None:
    """ Identifica a razão do bloqueio quando o IP não é global"""
    if ip_obj.is_loopback:
        return "loopback"
    if ip_obj.is_link_local:
        return "link_local"
    if ip_obj.is_private:
        return "private"
    if ip_obj.is_reserved:
        return "reserved"
    if ip_obj.is_multicast:
        return "multicast"
    if ip_obj.is_unspecified:
        return "unspecified"
    return "non_global"

def _validate_public_addresses(host: str, addresses: list[str]) -> list[str]:
    """ Valida se todos os IPs são globais antes de liberar o host """
    validated: list[str] = []
    for ip_text in addresses:
        try:
            ip_obj = ipaddress.ip_address(ip_text)
        except ValueError as exc:
            raise HostResolutionError(f"Endereço IP inválido para {host}") from exc
        
        if not ip_obj.is_global:
            reason = _classify_non_public(ip_obj)
            logger.warning(
                "dns_resolution_blocked",
                host=host,
                ip=ip_text,
                reason=reason,
            )
            raise HostResolutionError(f"Endereço não público bloqueado: {ip_text}")
        
        validated.append(ip_text)

    return sorted(set(validated))


__all__ = [
    "HostResolutionError",
    "build_timeout",
    "parse_retry_after",
    "resolve_public_address",
]
