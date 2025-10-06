""" Funções auxiliares para lidar com cabeçalhos HTTP e validações de host"""

from __future__ import annotations

import ipaddress
import socket
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Optional


def parse_retry_after(value: str) -> Optional[int]:
    """ Retorna o valor do cabeçalho Retry-after em segundos

    Suporta segundos inteiros ou data HTTP. Devolve ``None`` se a conversão falhar
    """
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
    
    A função tenta resolver o host para IPv4/IPv6. Cada endereço precisa ser
    global (``is_global``). Caso alguma IP pertença a uma faixa privada,
    loopback ou reservada, o host é rejeitado para evitar SSRF.
    """
    if not host:
        raise HostResolutionError("Host vazio não resolvido")
    
    try:
        addrinfo = socket.getaddrinfo(host, None, proto=socket.IPPROTO_TCP)
    except socket.gaierror as exc:
        raise HostResolutionError(f"Falha ao resolver host: {host}") from exc
    
    addresses: set[str] = set()
    for _, _, _, _, sockaddr in addrinfo:
        ip_text = sockaddr[0]
        try:
            ip_obj = ipaddress.ip_address(ip_text)
        except ValueError as exc:
            raise HostResolutionError(f"Endereço IP inválido para {host}") from exc
        
        if not ip_obj.is_global:
            raise HostResolutionError(f"Endereço não público bloqueado: {ip_text}")
        
        addresses.add(ip_text)

    if not addresses:
        raise HostResolutionError(f"Host sem endereços públicos: {host}")
    
    return sorted(addresses)

def resolve_public_addresses(host: str) -> list[str]:
    """ Expõe um alias em plural para compatibilidade com código e testes """
    #Mantemos o comportamento único para evitar duplicar lógica de resolução DNS
    return resolve_public_address(host)

__all__ = [
    "HostResolutionError",
    "extract_hostname",
    "parse_retry_after",
    "resolve_public_address",
    "resolve_public_addresses",
]
