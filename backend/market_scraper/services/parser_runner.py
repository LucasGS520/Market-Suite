""" Serviço auxiliar para executar parsers e sincronizar resultados 

As etapas do pipeline delegam a este módulo a responsabilidade de
invocar parsers, validar o payload e atualizar o contexto compartilhado
com os campos oficiais do contrato.
"""

from __future__ import annotations

from typing import Any, Callable, Mapping

import structlog

from shared.utils.logging_utils import sanitize_log_data

from market_scraper.services.synergic_pipeline import PipelineContext
from market_scraper.services.availability_inference import detect_availability
from market_scraper.utils.validator import DataQualityValidator


logger = structlog.get_logger("parser_runner")
ParserCallable = Callable[[str, str], Mapping[str, Any] | None]
_validator = DataQualityValidator()

def _update_shared_payload(context: PipelineContext, payload: Mapping[str, str]) -> None:
    """ Atualiza o ``shared_context`` apenas com campos oficializados """
    #Centralizamos a sincronização do payload para manter o contrato controlado
    context.data["name"] = payload["name"]
    context.data["current_price"] = payload["current_price"]
    context.data["currency"] = payload.get("currency")
    context.data["availability"] = payload.get("availability")
    context.data["last_status"] = payload.get("last_status")
    context.data["url"] = payload["url"]
    context.data["source"] = payload["source"]
    context.data["payload"] = dict(payload)
    context.data.setdefault("availability_inferred", payload.get("availability"))
    context.data.setdefault("last_status_inferred", payload.get("last_status"))

def run_parser_with_validation(
    *,
    parser: ParserCallable,
    context: PipelineContext,
    step_name: str,
) -> tuple[bool, dict[str, str] | None]:
    """ Executa parser, valida o resultado e atualiza o contexto quando válido """
    html = context.html or ""
    parser_name = getattr(parser, "__name__", parser.__class__.__name__)
    dump_path = context.data.get("dump_path")

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
            parser_name=parser_name,
        )
        context.data.setdefault("validation_failures", []).append({
            "step": step_name,
            "reason_code": "parser_error",
            "reason_message": "Erro interno durante execução do parser",
            "parser_name": parser_name,
            "dump_path": dump_path,
        })
        return False, None

    if not raw_payload:
        context.data.setdefault("validation_failures", []).append({
            "step": step_name,
            "reason_code": "parser_no_data",
            "reason_message": "Parser não encontrou dados extraíveis no HTML",
            "parser_name": parser_name,
            "dump_path": dump_path,
        })
        return False, None
    inferred_availability, inferred_last_status = detect_availability(
        html,
        status_code=context.data.get("http_status"),
        domain=context.source,
    )
    context.data["availability_inferred"] = inferred_availability
    context.data["last_status_inferred"] = inferred_last_status
    logger.info(
        "availability_inferred_before_validation",
        step=step_name,
        domain=context.source,
        availability=inferred_availability,
        last_status=inferred_last_status,
        url=sanitize_log_data(context.url),
    )
    validated = _validator.validate(
        step_name=step_name,
        payload=raw_payload,
        url=context.url,
        source=context.source,
        parser_name=parser_name,
        dump_path=dump_path,
        inferred_availability=inferred_availability,
        inferred_last_status=inferred_last_status,
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

    #Critério de aceite: dado útil = nome + preço (ou indisponibilidade explícita).
    #Payload estruturalmente válido sem preço não é suficiente para aceite final.
    if not validated.is_useful:
        logger.warning(
            "parser_data_not_useful",
            step=step_name,
            domain=context.source,
            reason_code="price_invalid",
            url=sanitize_log_data(context.url),
            parser_name=parser_name,
        )
        reason_entry = {
            "step": step_name,
            "reason_code": "price_invalid",
            "reason_message": "Dado útil requer nome e preço (ou indisponibilidade explícita)",
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
