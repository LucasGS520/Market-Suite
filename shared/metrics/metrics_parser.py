""" Métricas para operações de parsing de produtos 

Este módulo define contadores e histogramas utilizados para monitorar
o desempenho e a confiabilidade das etapas de parsing do projeto.
Cada métrica é rotulada pelo nome da biblioteca responsável pelo
processamento, permitindo identificar gargalos ou falhas específicas.
"""

from prometheus_client import Counter, Histogram

#Contador de sucesso por biblioteca utilizada no parsing
PARSER_SUCCESS_TOTAL = Counter(
    "parser_success_total",
    "Total de registros de produtos parseados com sucesso",
    ["library"],
)

#Contador de falha por biblioteca utilizada no parsing
PARSER_FAILURE_TOTAL = Counter(
    "parser_failure_total",
    "Total de falhas ao parser registros de produtos",
    ["library"]
)

#Histrograma de duração do parsing por biblioteca
PARSER_DURATION_SECONDS = Histogram(
    "parser_duration_seconds",
    "Tempo gasto em segundos durante o parsing por biblioteca",
    ["library"],
)

__all__ = [
    "PARSER_SUCCESS_TOTAL",
    "PARSER_FAILURE_TOTAL",
    "PARSER_DURATION_SECONDS",
]
