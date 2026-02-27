""" Configuração de logging para a API e workers do market_alert.

Centraliza dois contextos distintos de logging em funções claras:
- ``setup_api_logging()`` → para o processo FastAPI (main.py)
- ``setup_worker_logging()`` → para os workers Celery (celery_app.py)

Ambas delegam para a factory em ``shared/infra/logging``. A diferença
entre elas é que o worker adiciona filtros de eventos repetidos e silencia
loggers barulhentos de bibliotecas de infraestrutura.

Uso::

    # Em main.py
    from market_alert.core.logging_config import setup_api_logging
    setup_api_logging()

    # Em celery_app.py
    from market_alert.core.logging_config import setup_worker_logging
    setup_worker_logging()
"""

from __future__ import annotations

import structlog
from structlog.typing import BindableLogger, EventDict

from shared.infra.logging import configure_structlog


# Loggers de bibliotecas de infraestrutura que geram muito ruído nos workers.
# Mantidos em WARNING para que apenas erros reais apareçam nos logs operacionais.
WORKER_NOISY_LOGGERS: tuple[str, ...] = (
    "httpx",
    "httpcore",
    "anyio",
    "uvicorn",
    "asyncio",
    "celery",
    "celery.worker.pidbox",
    "celery.worker.pool",
    "celery.worker.consumer",
    "celery.worker.strategy",
    "celery.app.trace",
    "kombu",
)

# Eventos conhecidos que se repetem continuamente sem valor operacional.
_NOISY_EVENT_NAMES: frozenset[str] = frozenset({"channel_vars_missing"})

def drop_repeated_events(
    _logger: BindableLogger,
    _method_name: str,
    event_dict: EventDict,
) -> EventDict:
    """ Remove eventos que repetem ruído operacional sem informação nova.

    Processador structlog usado apenas no contexto do worker Celery.
    Adicionado via ``extra_processors`` em ``setup_worker_logging()``.
    """
    if event_dict.get("event") in _NOISY_EVENT_NAMES:
        raise structlog.DropEvent
    return event_dict


def setup_api_logging(log_level: str = "INFO") -> None:
    """ Configura logging estruturado JSON para o processo FastAPI.

    Deve ser chamada uma vez no startup da aplicação, antes de qualquer
    logger ser usado. Não silencia loggers de terceiros — o contexto da
    API não sofre do mesmo volume de ruído que os workers Celery.

    Args:
        log_level: Nível de log (ex.: "INFO", "DEBUG"). Padrão: "INFO".
    """
    configure_structlog(log_level=log_level)


def setup_worker_logging(log_level: str = "INFO") -> None:
    """ Configura logging estruturado JSON para workers Celery.

    Além da configuração base, adiciona:
    - Filtro ``drop_repeated_events`` para suprimir eventos repetitivos
    - Silenciamento de bibliotecas barulhentas (httpx, celery internals, etc.)

    Args:
        log_level: Nível de log (ex.: "INFO", "DEBUG"). Padrão: "INFO".
    """
    configure_structlog(
        log_level=log_level,
        extra_processors=(drop_repeated_events,),
        noisy_loggers=WORKER_NOISY_LOGGERS,
    )
