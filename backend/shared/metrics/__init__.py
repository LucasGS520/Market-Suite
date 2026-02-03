""" Pacote centralizador de métricas Prometheus.

Este pacote expõe as métricas agrupadas por domínio para que os
serviços possam importá-las de forma organizada.

Quando ENABLE_METRICS=0, retorna implementações no-op que preservam
a API mas não coletam dados.
"""

import os

# Verifica se métricas estão habilitadas
ENABLE_METRICS = os.getenv("ENABLE_METRICS", "0") in {"1", "true", "True", "yes"}

# Se métricas desabilitadas, usa stubs no-op
if ENABLE_METRICS:
    from prometheus_client import Counter, Gauge, Histogram, Summary, Info, Enum
else:
    from shared.metrics_noop import Counter, Gauge, Histogram, Summary, Info, Enum

# Importa os módulos de métricas (sempre necessário para preservar a API)
from . import (
    metrics_celery,
    metrics_scraper,
    metrics_cache,
    metrics_audit,
    metrics_auth,
    metrics_price_comparison,
    metrics_http,
    metrics_db,
    metrics_parser,
    metrics_recheck,
    metrics_logging,
    metrics_api,
    metrics_redis,
    metrics_products,
    metrics_notifications,
    metrics_settings,
    metrics_priority_queue,
)

from .metrics_celery import *
from .metrics_scraper import *
from .metrics_cache import *
from .metrics_audit import *
from .metrics_auth import *
from .metrics_price_comparison import *
from .metrics_http import *
from .metrics_db import *
from .metrics_parser import *
from .metrics_recheck import *
from .metrics_logging import *
from .metrics_api import *
from .metrics_redis import *
from .metrics_products import *
from .metrics_notifications import *
from .metrics_settings import *
from .metrics_priority_queue import *

__all__ = (
    ["ENABLE_METRICS", "Counter", "Gauge", "Histogram", "Summary", "Info", "Enum"]
    + metrics_celery.__all__
    + metrics_scraper.__all__
    + metrics_cache.__all__
    + metrics_audit.__all__
    + metrics_auth.__all__
    + metrics_price_comparison.__all__
    + metrics_http.__all__
    + metrics_db.__all__
    + metrics_parser.__all__
    + metrics_recheck.__all__
    + metrics_logging.__all__
    + metrics_api.__all__
    + metrics_redis.__all__
    + metrics_products.__all__
    + metrics_notifications.__all__
    + metrics_settings.__all__
    + metrics_priority_queue.__all__
)
