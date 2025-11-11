""" Administra metadados condicionais (ETag/Last-Modified) das respostas de parsing

O módulo centraliza a geração do hash do payload final, armazenamento em cache
e leitura dos cabeçalhos condicionais. Dessa forma o endpoint pode responder
``304 Not Modified`` com segurança e reutilizar o mesmo contrato compartilhado
sem replicar lógica de serialização.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from email.utils import format_datetime, parsedate_to_datetime
from typing import Any, Mapping

import structlog

from market_scraper.core.config_scraper import settings
from market_scraper.utils import cache
from backend.shared.schemas.shared_schemas_scraper import ParserResponse


logger = structlog.get_logger("conditional_payload")

@dataclass(slots=True)
class CachedResponseMetadata:
    """ Agrupa dados necessários para validar respostas condicionais """
    etag: str
    last_modified: datetime
    payload: ParserResponse

    @property
    def quoted_etag(self) -> str:
        """ Retorna ETag formatado conforme o cabeçalho HTTP """
        return f'"{self.etag}"'
    
    @property
    def http_last_modified(self) -> str:
        """ Formata ``Last-Modified`` seguindo RFC 7231 """
        return format_datetime(self.last_modified, usegmt=True)
    
_CACHE_KEY_PREFIX = "payload::"
_CACHE_CONTROL_DIRECTIVE = "max-age=0, must-revalidate"

def _cache_key(url: str) -> str:
    """ Cria a chave de cache única para o recurso informado """
    return f"{_CACHE_KEY_PREFIX}{url}"

def _canonical_payload_dump(response: ParserResponse) -> str:
    """ Serializa o payload garantindo ordem determinística para o hash """
    #Utilizamos ``mode='json'`` para converter ``Decimal`` em string e manter consistência entre execuções
    dumped = response.model_dump(mode="json", exclude_none=True)
    return json.dumps(dumped, default=str, sort_keys=True, separators=(",", ":"))

def _compute_etag(response: ParserResponse) -> str:
    """ Calcula hash estável a partir do payload final do scraper """
    payload_dump = _canonical_payload_dump(response)
    digest = hashlib.sha256(payload_dump.encode("utf-8")).hexdigest()
    return digest

def store_response(url: str, response: ParserResponse) -> CachedResponseMetadata:
    """ Armazena payload bem-sucedido no cache e devolve os metadados """
    etag = _compute_etag(response)
    last_modified = datetime.now(timezone.utc).replace(microsecond=0)
    cache_payload: dict[str, Any] = {
        "etag": etag,
        "last_modified": last_modified.isoformat(),
        "payload": response.model_dump(mode="json", exclude_none=True),
    }
    cache.set(_cache_key(url), cache_payload, settings.SCRAPER_CACHE_TTL_SECONDS)
    return CachedResponseMetadata(etag=etag, last_modified=last_modified, payload=response)

def get_cached_response(url: str) -> CachedResponseMetadata | None:
    """ Recupera payload anteriormente armazenado quando ainda válido """
    cached = cache.get(_cache_key(url))
    if not isinstance(cached, Mapping):
        return None
    
    etag = cached.get("etag")
    last_modified_raw = cached.get("last_modified")
    payload_data = cached.get("payload")

    if not etag or not last_modified_raw or payload_data is None:
        return None
    
    try:
        last_modified = datetime.fromisoformat(last_modified_raw)
    except ValueError:
        logger.warning("invalid_cached_last_modified", value=last_modified_raw)
        return None
    
    try:
        payload = ParserResponse.model_validate(payload_data)
    except Exception as exc:
        logger.warning("invalid_cached_payload", error=str(exc))
        return None

    if last_modified.tzinfo is None:
        last_modified = last_modified.replace(tzinfo=timezone.utc)
    else:
        last_modified = last_modified.astimezone(timezone.utc)

    return CachedResponseMetadata(etag=etag, last_modified=last_modified, payload=payload)

def invalidate_cached_response(url: str) -> None:
    """ Remove explicitamente a resposta condicionada da URL fornecida """
    cache.invalidate(_cache_key(url))

def parse_if_modified_since(header_value: str | None) -> datetime | None:
    """ Traduz ``If-Modified-Since`` em ``datetime`` UTC quando possível """
    if not header_value:
        return None
    
    try:
        parsed = parsedate_to_datetime(header_value)
    except (TypeError, ValueError):
        logger.warning("invalid_if_modified_since_header", value=header_value)
        return None
    
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)

def match_if_none_match(header_value: str | None, etag: str) -> bool:
    """ Confere se o ``If-None-Match`` recebido corresponde ao ETag atual """
    if not header_value:
        return False
    
    header_value = header_value.strip()
    if header_value == "*":
        return True
    
    candidates: list[str] = []
    for part in header_value.split(","):
        cleaned = part.strip()
        if cleaned.startswith("W/"):
            cleaned = cleaned[2:].lstrip()
        candidates.append(cleaned.strip('"'))
    return etag in candidates

def should_return_not_modified(
    *,
    if_none_match: str | None,
    if_modified_since: datetime | None,
    metadata: CachedResponseMetadata,
) -> bool:
    """ Aplica regras HTTP para decidir se a resposta pode ser 304 """
    if match_if_none_match(if_none_match, metadata.etag):
        return True
    
    if if_none_match:
        #Quando ``If-None-Match`` está presente mas não casou, ignoramos o ``If-Modified-Since`` por compatibilidade com RFC 7232
        return False
    
    if if_modified_since and metadata.last_modified <= if_modified_since:
        return True
    
    return False

def build_cache_headers(metadata: CachedResponseMetadata) -> dict[str, str]:
    """ Monta cabeçalhos HTTP utilizados tanto em 200 quanto 304 """
    return {
        "ETag": metadata.quoted_etag,
        "Last-Modified": metadata.http_last_modified,
        "Cache-Control": _CACHE_CONTROL_DIRECTIVE,
    }


__all__ = [
    "CachedResponseMetadata",
    "build_cache_headers",
    "get_cached_response",
    "invalidate_cached_response",
    "match_if_none_match",
    "parse_if_modified_since",
    "should_return_not_modified",
    "store_response",
]
