""" Métricas para operações de parsing de produtos """

from prometheus_client import Counter

PARSER_SUCCESS_TOTAL = Counter(
    "parser_success_total",
    "Total de registros de produtos parseados com sucesso",
)

PARSER_FAILURE_TOTAL = Counter(
    "parser_failure_total",
    "Total de falhas ao parser registros de produtos",
)

__all__ = [
    "PARSER_SUCCESS_TOTAL",
    "PARSER_FAILURE_TOTAL",
]
