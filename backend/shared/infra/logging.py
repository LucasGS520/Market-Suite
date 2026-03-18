""" Factory de configuração de logging estruturado para todos os serviços.

Centraliza a configuração do structlog em um único lugar. Cada serviço
chama ``configure_structlog()`` passando seus parâmetros específicos,
eliminando a duplicação de código entre API e worker.

Uso::

    # Em qualquer serviço (API ou worker)
    from shared.infra.logging import configure_structlog

    configure_structlog(
        log_level="INFO",
        extra_processors=(meu_filtro,),
        noisy_loggers=("httpx", "kombu"),
    )
"""

from __future__ import annotations

import logging
from typing import Any, Sequence

import structlog
from structlog.typing import EventDict, Processor, WrappedLogger


def _inject_trace_id(
    logger: WrappedLogger, method_name: str, event_dict: EventDict
) -> EventDict:
    """ Processor structlog: injeta trace_id do ContextVar em todos os eventos de log.

    Lê o valor atual de ``trace_id`` da ContextVar (definida via
    ``shared.utils.trace_context.set_trace_id``) e o adiciona ao evento
    somente se não houver um valor explícito já presente. Dessa forma,
    chamadas que passam ``trace_id=`` explicitamente preservam seu valor.

    Não propaga exceções — se a leitura do ContextVar falhar, o log
    prossegue sem o campo.
    """
    if "trace_id" not in event_dict:
        try:
            from shared.utils.trace_context import get_trace_id
            tid = get_trace_id()
            if tid:
                event_dict["trace_id"] = tid
        except Exception:
            pass
    return event_dict


def configure_structlog(
    *,
    log_level: str = "INFO",
    extra_processors: Sequence[Processor] = (),
    noisy_loggers: Sequence[str] = (),
) -> None:
    """ Configura structlog com saída JSON estruturada.

    Deve ser chamada uma vez no startup do processo, antes de qualquer
    ``structlog.get_logger()`` ser usado para logar mensagens.

    Args:
        log_level: Nível de log para o root logger (ex.: "INFO", "DEBUG").
            Aceita qualquer nível válido do módulo ``logging``.
        extra_processors: Processadores adicionais inseridos antes do
            ``JSONRenderer``. Útil para filtros específicos de contexto,
            como ``drop_repeated_events`` no worker Celery.
        noisy_loggers: Nomes de loggers que devem usar nível WARNING,
            reduzindo ruído de bibliotecas de infraestrutura nos logs.
    """
    processors: list[Processor] = [
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        _inject_trace_id,
        *extra_processors,
        structlog.processors.JSONRenderer(),
    ]

    structlog.configure(
        processors=processors,
        wrapper_class=structlog.stdlib.BoundLogger,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )

    handler = logging.StreamHandler()
    handler.setFormatter(structlog.stdlib.ProcessorFormatter(
        processor=structlog.processors.JSONRenderer(),
        foreign_pre_chain=[structlog.processors.TimeStamper(fmt="iso")],
    ))

    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(getattr(logging, log_level.upper(), logging.INFO))

    for logger_name in noisy_loggers:
        logging.getLogger(logger_name).setLevel(logging.WARNING)
