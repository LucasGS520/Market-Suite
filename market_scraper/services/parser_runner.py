""" Serviço auxiliar para executar parsers e sicronizar resultados 

As etapas do pipeline delegam a este módulo a responsabilidade de
invocar parsers, validar o payload e atualizar o contexto compartilhado
com os campos oficiais do contrato.
"""

from __future__ import annotations

from typing import Any, Callable, Mapping

import structlog

from shared.utils.logging_utils import sanitize_log_data

from market_scraper.services.synergic_pipeline import PipelineContext
from market_scraper.utils.validator import DataQualityValidator


logger = structlog.get_logger("parser_runner")
ParserCallable = Callable[[str, str], Mapping[str, Any] | None]
_validator = DataQualityValidator()

def _update_shared_payload(context: PipelineContext, payload: Mapping[str, str]) -> None:
    """ Atualiza o ``shared_context`` apenas com campos oficializados """
    #Centralizamos a sincronização do payload para manter o contrato controlado
    context.data["name"] = payload["name"]
    context.data["current_price"] = payload["current_price"]
    context.data["url"] = payload["url"]
    context.data["source"] = payload["source"]
    context.data["payload"] = dict(payload)

def run_parser_with_validation(
    *,
    parser: ParserCallable,
    context: PipelineContext,
    step_name: str,
) -> tuple[bool, dict[str, str] | None]:
    """ Executa parser, valida o resultado e atualiza o contexto quando válido """
    html = context.html or ""
    try:
        raw_payload = parser(html, context.url)
    except Exception as exc:
        logger.warning(
            "parser_execution_error",
            step=step_name,
            domain=context.source,
            duration_ms=0.0,
            result="error",
            url=sanitize_log_data(context.url),
            error=sanitize_log_data(str(exc)),
        )
        return False, None
    
    if not raw_payload:
        return False, None
    
    parser_name = getattr(parser, "__name__", parser.__class__.__name__)
    dump_path = context.data.get("dump_path")
    validated = _validator.validate(
        step_name=step_name,
        payload=raw_payload,
        url=context.url,
        source=context.source,
        parser_name=parser_name,
        dump_path=dump_path,
    )
    if not validated.is_valid:
        reason_entry = {
            "step": step_name,
            "reason_code": validated.reason_code,
            "reason_message": validated.reason_message,
            "parser_name": parser_name,
            "dump_path": dump_path,
        }
        context.data.setdefault("validation_failures", []).append(reason_entry)
        return False, None

    payload = validated.payload or {}
    _update_shared_payload(context, payload)
    return True, payload


__all__ = [
    "ParserCallable",
    "run_parser_with_validation",
]
