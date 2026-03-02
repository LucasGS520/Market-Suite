""" Normalização de payloads de scraping para o contrato ``ParserResponse`` """

from __future__ import annotations

from typing import Any, Mapping

import structlog
from pydantic import BaseModel, ValidationError

from shared.schemas import ParserResponse


logger = structlog.get_logger(__name__)

def _extract_schema_version(payload: Any) -> Any:
    """ Extrai ``schema_version`` de mapeamentos ou objetos com atributo homônimo """
    if isinstance(payload, Mapping):
        return payload.get("schema_version")
    return getattr(payload, "schema_version", None)

def normalize_scraper_response(
    payload: ParserResponse | BaseModel | Mapping[str, Any] | str,
    *,
    source: str,
    request_id: str | None = None,
    correlation_id: str | None = None,
) -> ParserResponse:
    """ Normaliza e valida a entrada do pipeline de scraping em ``ParserResponse``.

    Este utilitário define o contrato de fronteira entre produtor e consumidor
    do pipeline: qualquer resposta suportada (``dict``, string JSON ou objeto
    Pydantic) é convertida para um único tipo canônico validado. A centralização
    evita divergências de import/validação entre cliente HTTP e worker Celery,
    reduzindo regressões em mudanças de schema.
    """
    payload_type = type(payload).__name__
    schema_version = _extract_schema_version(payload)

    if isinstance(payload, str):
        try:
            return ParserResponse.model_validate_json(payload)
        except ValidationError:
            logger.warning(
                "scraper_response_normalization_failed",
                source=source,
                payload_type=payload_type,
                schema_version=schema_version,
                request_id=request_id,
                correlation_id=correlation_id,
            )
            raise

    raw_payload: Any = payload

    if isinstance(raw_payload, BaseModel):
        raw_payload = raw_payload.model_dump(mode="json")

    try:
        return ParserResponse.model_validate(raw_payload)
    except ValidationError:
        logger.warning(
            "scraper_response_normalization_failed",
            source=source,
            payload_type=payload_type,
            schema_version=schema_version,
            request_id=request_id,
            correlation_id=correlation_id,
        )
        raise


__all__ = ["normalize_scraper_response"]
