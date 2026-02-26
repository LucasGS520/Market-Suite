""" Funções compartilhadas para derivar nomes de produtos via URL/scraping. """

from __future__ import annotations
from urllib.parse import unquote, urlparse
from shared.utils import sanitize_text


def derive_name_from_url(url: str, *, fallback: str = "Produto") -> str:
    """ Extrai um identificador legível da URL quando nome não é informado. """
    parsed = urlparse(url)
    #Usa o último segmento do path como primeira tentativa de nome.
    path_segment = unquote(parsed.path or "").strip("/")
    last_piece = path_segment.split("/")[-1] if path_segment else ""
    candidate = last_piece or parsed.netloc or str(url)
    normalized = candidate.replace("-", " ").replace("_", " ").strip()
    sanitized = sanitize_text(normalized)
    if sanitized:
        return sanitized

    host = sanitize_text(parsed.netloc)
    if host:
        return host

    #Fallback final evita persistir nomes vazios no banco.
    return fallback

def prepare_effective_name(
    provided: str | None,
    scraped: str | None,
    url: str,
    *,
    fallback_label: str,
) -> tuple[str, str]:
    """ Define nome efetivo seguindo prioridade usuário -> scraping -> URL. """
    fallback_name = derive_name_from_url(url, fallback=fallback_label)
    sanitized_provided = sanitize_text(provided) if provided else None
    sanitized_scraped = sanitize_text(scraped)
    if sanitized_provided:
        return sanitized_provided, fallback_name
    if sanitized_scraped:
        return sanitized_scraped, fallback_name
    return fallback_name, fallback_name

def should_replace_with_scraped(
    existing: str | None,
    fallback: str,
    scraped: str | None,
) -> bool:
    """ Decide se nome atual (fallback) deve ser trocado por nome raspado. """
    sanitized_scraped = sanitize_text(scraped)
    if not sanitized_scraped:
        return False
    if existing is None:
        return True
    return existing.strip().casefold() == fallback.strip().casefold()
