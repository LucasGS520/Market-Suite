""" Factory de logger estruturado para o market_scraper.

Centraliza configuração de contexto obrigatório (trace_id, domain, stage)
e garante que todos os loggers do módulo compartilhem a mesma convenção de
campos estruturados.

Uso:

    from market_scraper.infra.logging.structured_logger import get_scraper_logger

    logger = get_scraper_logger("meu_modulo")
    logger.info("evento", trace_id=trace_id, domain=domain, stage="collect")

    # Ou com contexto pré-vinculado:
    bound = bind_request_context(logger, trace_id=trace_id, domain=domain)
    bound.info("evento", stage="collect")
"""

from __future__ import annotations

import structlog
from structlog.stdlib import BoundLogger


def get_scraper_logger(name: str) -> BoundLogger:
    """Retorna logger structlog nomeado para o componente informado.

    O nome aparece nos logs como ``logger`` e facilita filtrar por camada
    (e.g. "collection", "extraction", "post_processing").
    """
    return structlog.get_logger(name)


def bind_request_context(
    logger: BoundLogger,
    *,
    trace_id: str | None = None,
    domain: str | None = None,
    url: str | None = None,
) -> BoundLogger:
    """Vincula contexto de requisição ao logger retornado.

    Campos vinculados aparecem em todos os eventos subsequentes emitidos
    pelo logger retornado — sem precisar repeti-los por chamada.
    """
    ctx: dict[str, str] = {}
    if trace_id is not None:
        ctx["trace_id"] = trace_id
    if domain is not None:
        ctx["domain"] = domain
    if url is not None:
        ctx["url"] = url
    return logger.bind(**ctx)


def bind_stage_context(logger: BoundLogger, *, stage: str) -> BoundLogger:
    """Vincula o nome do estágio do pipeline ao logger para rastreamento."""
    return logger.bind(stage=stage)


__all__ = [
    "get_scraper_logger",
    "bind_request_context",
    "bind_stage_context",
]
