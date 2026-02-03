""" Testes para métricas de parsing de blbiotecas """

import os
import pytest

# Importa REGISTRY condicionalmente
_ENABLE_METRICS = os.getenv("ENABLE_METRICS", "0") in {"1", "true", "True", "yes"}
if _ENABLE_METRICS:
    from prometheus_client import REGISTRY
else:
    from shared.metrics_noop import REGISTRY

from shared.metrics.metrics_parser import PARSER_FAILURE_TOTAL, PARSER_SUCCESS_TOTAL, PARSER_DURATION_SECONDS


@pytest.mark.skipif(not _ENABLE_METRICS, reason="Metrics disabled")
def test_parser_metrics_increment_e_observe():
    """ Garante incremento e observação das métricas de parsing """
    PARSER_SUCCESS_TOTAL.clear()
    PARSER_FAILURE_TOTAL.clear()
    PARSER_DURATION_SECONDS.clear()

    PARSER_SUCCESS_TOTAL.labels(library="extruct").inc()
    PARSER_FAILURE_TOTAL.labels(library="parsel").inc()
    PARSER_DURATION_SECONDS.labels(library="extruct").observe(0.5)

    sucesso = REGISTRY.get_sample_value(
        "parser_success_total", {"library": "extruct"}
    )
    falha = REGISTRY.get_sample_value(
        "parser_failure_total", {"library": "parsel"}
    )
    duracao = REGISTRY.get_sample_value(
        "parser_duration_seconds_sum", {"library": "extruct"}
    )
    contagem = REGISTRY.get_sample_value(
        "parser_duration_seconds_count", {"library": "extruct"}
    )

    assert sucesso == 1.0
    assert falha == 1.0
    assert duracao == 0.5
    assert contagem == 1.0