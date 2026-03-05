""" Funções utilitárias para interpretar metadados retornados pelo scraper. """

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING, Any, Mapping

from pydantic import ValidationError

from shared.utils.http_headers import normalize_headers, parse_http_datetime

if TYPE_CHECKING:
    #Importar apenas em tempo de análise evita dependência circular em runtime
    from shared.schemas import ParserResponse
else:  #pragma: no cover - rótulo evita alerta de cobertura em fallback
    ParserResponse = object

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
    payload: "ParserResponse | Mapping[str, Any] | Any",
    headers: Mapping[str, str],
) -> ScraperMetadata:
    """ Extrai metadados do retorno do scraper com validação resiliente de schema.

    Aceita como entrada um ``ParserResponse``, ``dict`` ou qualquer objeto
    serializável via ``model_dump``/``dict``. O conteúdo é normalizado por
    ``ParserResponse.model_validate`` para garantir contrato único antes de
    acessar campos derivados. Em caso de falha real de schema, lança
    ``ValueError`` com contexto do tipo recebido e erros de validação.
    """
    from shared.schemas import ParserResponse

    raw_payload: Any = payload
    if not isinstance(payload, Mapping):
        if hasattr(payload, "model_dump"):
            raw_payload = payload.model_dump()
        elif hasattr(payload, "dict"):
            raw_payload = payload.dict()

    try:
        #A validação por schema evita falsos negativos de isinstance quando o mesmo modelo é carregado por caminhos/módulos diferentes em runtime.
        normalized_payload = ParserResponse.model_validate(raw_payload)
    except ValidationError as exc:
        payload_type = type(payload).__name__
        raise ValueError(
            "payload inválido para ParserResponse em extract_scraper_metadata "
            f"(tipo recebido: {payload_type})"
        ) from exc
    
    extras = dict(normalized_payload.payload or {})
    extras.setdefault("availability", normalized_payload.availability)
    extras.setdefault("last_status", normalized_payload.last_status)
    extras.setdefault("currency", normalized_payload.currency)
    extras.setdefault("etag", normalized_payload.etag)
    extras.setdefault("not_modified", normalized_payload.not_modified)
    normalized = normalize_headers(headers)
    return ScraperMetadata(
        extras=extras,
        headers=normalized,
    )


__all__ = [
    "ScraperMetadata",
    "extract_scraper_metadata",
]
