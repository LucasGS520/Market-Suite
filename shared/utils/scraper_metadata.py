""" Funções auxiliares para interpretar metadados vindos do scraper """

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Mapping

from shared.utils.http_headers import normalize_headers, parse_http_datetime


@dataclass(slots=True)
class ScraperMetadata:
    """ Agrupa metadados extras e cabeçalhos normalizados do scraper """
    extras: dict[str, Any]
    headers: dict[str, str]

    def get(self, key: str, default: Any | None = None) -> Any | None:
        """ Obtém valor buscando primeiro nos extras e depois nos headers """
        if key in self.extras:
            return self.extras[key]
        return self.headers.get(key, default)
    
    @property
    def etag(self) -> str | None:
        """ Retorna o ``ETag`` considerando aliases comuns """
        return (
            self.extras.get("etag")
            or self.headers.get("etag")
            or self.headers.get("if-none-match")
        )
    
    @property
    def last_modified(self) -> datetime | None:
        """ Converte cabeçalhos ``Last-Modified`` em ``datetime`` UTC """
        raw_value = (
            self.extras.get("last_modified")
            or self.extras.get("last-modified")
            or self.headers.get("last_modified")
            or self.headers.get("last-modified")
        )
        return parse_http_datetime(raw_value)
    
def extract_scraper_metadata(
    payload: "ParserResponse",
    headers: Mapping[str, str],
) -> ScraperMetadata:
    """ Monta ``ScraperMetadata`` a partir do payload e dos cabeçalhos """
    from shared.schemas.schemas_scraper import ParserResponse

    if not isinstance(payload, ParserResponse):
        raise TypeError("payload precisa ser ParserResponse")
    
    extras = dict(payload.payload or {})
    normalized = normalize_headers(headers)
    return ScraperMetadata(
        extras=extras,
        headers=normalized,
    )


__all__ = [
    "ScraperMetadata",
    "extract_scraper_metadata",
]
