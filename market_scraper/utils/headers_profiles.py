""" Constrói perfis de headers HTTP coerentes para os User-Agents do scraper

O módulo associa cadeias de User-Agent a combinações de headers que
imitam navegadores modernos. Dessa forma reduzimos rejeições causadas
por bundles artificiais e centralizamos a lógica em um único ponto para
reuso pelo FetchHTMLStep.
"""

from __future__ import annotations

import re
from functools import lru_cache
from typing import Dict, Iterable, Tuple

from market_scraper.core.config_scraper import settings


__all__ = ["compose_headers"]

#Headers compartilhados por todas as requisições de navegação
_COMMON_NAVIGATION_PAIRS: Tuple[Tuple[str, str], ...] = (
    ("Cache-Control", "max-age=0"),
    ("Pragma", "no-cache"),
    ("Upgrade-Insecure-Requests", "1"),
    ("Accept-Encoding", "gzip, deflate, br"),
    ("Sec-Fetch-Dest", "document"),
    ("Sec-Fetch-Mode", "navigate"),
    ("Sec-Fetch-Site", "none"),
    ("Sec-Fetch-User", "?1"),
)

_CHROME_VERSION_RE = re.compile(r"Chrome/(\d+)")

def compose_headers(user_agent: str, *, referer: str | None = None) -> Dict[str, str]:
    """ Gera o bundle completo de headers para o User-Agent informado
    
    Args:
        user_agent: cadeia de User-Agent que será enviada na requisição
        referer: valor opcional para o header Referer

    Returns:
        Dicionário com headers prontos para consumo pelo client HTTP
    """
    headers = {
        "User-Agent": user_agent,
        "Accept": settings.SCRAPER_HEADERS_ACCEPT,
        "Accept-Language": settings.SCRAPER_HEADERS_ACCEPT_LANGUAGE,
        "Connection": settings.SCRAPER_HEADERS_CONNECTION,
    }

    headers.update(_pairs_to_dict(_COMMON_NAVIGATION_PAIRS))
    headers.update(_pairs_to_dict(_profile_specific_pairs(user_agent)))

    if referer:
        headers["Referer"] = referer

    return headers

@lru_cache(maxsize=32)
def _profile_specific_pairs(user_agent: str) -> Tuple[Tuple[str, str], ...]:
    """ Determina headers adicionais coerentes ao navegador deduzido """
    if _is_chrome_family(user_agent):
        return _build_chrome_pairs(user_agent)
    
    if "Firefox/" in user_agent:
        return (
            ("TE", "trailers"),
            ("DNT", "1"),
        )
    
    if "iPhone" in user_agent or "Mobile/" in user_agent:
        #Safari mobile não envia client hints adicionais
        return tuple()
    
    #Safari desktop e navegadores menos comuns utilizam somente conjunto comum
    return tuple()

def _build_chrome_pairs(user_agent: str) -> Tuple[Tuple[str, str], ...]:
    """ Constrói client hints compatíveis com navegadores Chrome """
    major_version = _extract_major_version(user_agent)
    platform = _detect_platform(user_agent)
    mobile_flag = _is_mobile(user_agent)

    pairs = [
        ("Sec-CH-UA-Mobile", "?1" if mobile_flag else "?0"),
    ]

    if platform:
        pairs.append(("Sec-CH-UA-Platform", f'"{platform}"'))

    if major_version:
        sec_ch_ua = (
            f'"Not A(Brand";v="8", "Chromium";v="{major_version}", '
            f'"Google Chrome";v="{major_version}"'
        )
        pairs.append(("Sec-CH-UA", sec_ch_ua))

    return tuple(pairs)

def _is_chrome_family(user_agent: str) -> bool:
    """ Identifica cadeias compatíveis com navegadores baseados em Chromium """
    if "Chrome/" not in user_agent:
        return False
    
    if "Edg/" in user_agent or "OPR/" in user_agent:
        #Edge e Opera utilizam cabeçalhos específicos, mantemos fora até termos pool dedicado
        return False
    
    return "Chrom" in user_agent or "Safari/" in user_agent

def _extract_major_version(user_agent: str) -> str | None:
    """ Obtém a versão principal do navegador Chrome para montar o client hint """
    match = _CHROME_VERSION_RE.search(user_agent)
    if not match:
        return None
    
    return match.group(1)

def _detect_platform(user_agent: str) -> str | None:
    """ Mapeia plataforma para client hint Sec-CH-UA-Platform """
    if "Windows" in user_agent:
        return "Windows"
    if "Linux" in user_agent and "Android" not in user_agent:
        return "Linux"
    if "Macintosh" in user_agent:
        return "macOS"
    if "Android" in user_agent:
        return "Android"
    if "iPhone" in user_agent or "iPad" in user_agent:
        return "iOS"
    return None

def _is_mobile(user_agent: str) -> bool:
    """ Detecta se o User-Agent representa dispositivo móvel """
    lowered = user_agent.lower()
    return "mobile" in lowered or "iphone" in lowered or "android" in lowered

def _pairs_to_dict(pairs: Iterable[Tuple[str, str]]) -> Dict[str, str]:
    """ Converte tuplas de pares em dicionário copiando os valores """
    return {key: value for key, value in pairs}
