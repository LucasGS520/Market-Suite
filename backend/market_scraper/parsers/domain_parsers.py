""" Mapeamento de parsers específicos por domínio suportado pelo scraper """

from __future__ import annotations

from typing import Any, Callable, Mapping

from market_scraper.parsers import (
    parse_amazon_html,
    parse_magalu_html,
    parse_meli_html,
)


ParserCallable = Callable[[str, str], Mapping[str, Any] | None]

#O mapeamento por sufixo evita duplicar lógica de detcção para cada subdomínio
_DOMAIN_PARSERS_SUFFIXES: tuple[tuple[str, ParserCallable], ...] = (
    ("mercadolivre.com.br", parse_meli_html),
    ("mercadolivre.com", parse_meli_html),
    ("amazon.com.br", parse_amazon_html),
    ("amazon.com", parse_amazon_html),
    ("magazineluiza.com.br", parse_magalu_html),
    ("magazineluiza.com", parse_magalu_html),
)

def get_domain_parser(domain: str | None) -> tuple[str, ParserCallable] | None:
    """ Retorna o parser apropriado com base no sufixo do domínio informado """
    normalized = (domain or "").strip().lower()
    if not normalized:
        return None
    
    for suffix, parser in _DOMAIN_PARSERS_SUFFIXES:
        #Permitimos match por igualdade ou sufixo para cobrir subdomínios dinâmicos
        if normalized == suffix or normalized.endswith(f".{suffix}"):
            return suffix, parser
    return None


__all__ = [
    "ParserCallable",
    "get_domain_parser",
]
