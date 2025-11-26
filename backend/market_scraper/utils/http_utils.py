""" Funções auxiliares para lidar com cabeçalhos HTTP, timeouts e validações de host

Este módulo centraliza utilidades usadas por diferentes etapas do pipeline,
com destaque para validação de cabeçalhos como ``Retry-After``, configuração
de timeouts aderentes às políticas globais e resolução segura de hosts para prevenir SSRF.
"""

from __future__ import annotations

import gzip
import io
import ipaddress
import socket
import threading
import time
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeout
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Optional
import zlib

import httpx
import structlog

from market_scraper.core.config_scraper import settings
from shared.metrics.metrics_scraper import (
    SCRAPER_DNS_BLOCKED_TOTAL,
    SCRAPER_DNS_RESOLVE_DURATION_SECONDS,
)


logger = structlog.get_logger(__name__)

#Cache de DNS simples potegido por lock para reduzir round-trips repetidos e evitar condições de corrida entre threads do pipeline
_DNS_CACHE: dict[str, tuple[float, list[str]]] = {}
_DNS_CACHE_LOCK = threading.Lock()

try:
    import brotli as _brotli_lib
except ModuleNotFoundError:
    _brotli_lib = None

try:
    from brotlicffi import decompress as _brotlicffi_decompress
except ModuleNotFoundError:
    _brotlicffi_decompress = None

class ContentDecodeError(Exception):
    """ Sinaliza falhas ao transformar o corpo HTTP em texto legível """
    def __init__(self, *, encoding: str, reason: str) -> None:
        #Armazenamos o encoding e o motivo para facilitar logs e métricas
        super().__init__(f"{reason} (encoding={encoding})")
        self.encoding = encoding
        self.reason = reason

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

def _decompress_brotli(payload: bytes) -> bytes:
    """ Aplica descompressão Brotli usando a biblioteca disponível """
    if _brotli_lib is not None:
        return _brotli_lib.decompress(payload)
    if _brotlicffi_decompress is not None:
        return _brotlicffi_decompress(payload)
    raise ContentDecodeError(encoding="br", reason="brotli_missing")

def _decompress_gzip(payload: bytes) -> bytes:
    """ Manipula payloads gzip utilizando buffer de memória """
    buffer = io.BytesIO(payload)
    with gzip.GzipFile(fileobj=buffer) as gz_file:
        return gz_file.read()
    
def _decompress_deflate(payload: bytes) -> bytes:
    """ Processa corpos codificados com deflate respeitando RFC 1950 """
    try:
        return zlib.decompress(payload)
    except zlib.error:
        #Alguns servidores enviam deflate cru sem cabeçalho zlib
        return zlib.decompress(payload, -zlib.MAX_WBITS)
    
def decode_http_body(response: httpx.Response, *, default_encoding: str = "utf-8") -> str:
    """ Converte a resposta HTTP para texto tratando Content-Encoding """
    try:
        #Primeira tentativa delega ao httpx, que já inclui heurísticas de charset
        return response.text
    except (httpx.DecodingError, UnicodeDecodeError):
        #Seguimos para a decodificaçã manual apenas quando a API padrão falha
        pass

    content_encoding = (response.headers.get("Content-Encoding") or "identity").lower()
    payload = response.content

    try:
        if "br" in content_encoding:
            payload = _decompress_brotli(payload)
        elif "gzip" in content_encoding:
            payload = _decompress_gzip(payload)
        elif "deflate" in content_encoding:
            payload = _decompress_deflate(payload)
    except ContentDecodeError:
        raise
    except Exception as exc:
        raise ContentDecodeError(encoding=content_encoding, reason="decompress_failed") from exc
    
    encoding = response.encoding or response.charset or default_encoding
    try:
        return payload.decode(encoding)
    except Exception as exc:
        raise ContentDecodeError(encoding=encoding, reason="decode_failed") from exc

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
    """Identifica a razão do bloqueio quando o IP não é global"""
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
            SCRAPER_DNS_BLOCKED_TOTAL.labels(reason=reason).inc()
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
    "ContentDecodeError",
    "extract_hostname",
    "parse_retry_after",
    "resolve_public_address",
    "resolve_public_addresses",
    "decode_http_body",
]
