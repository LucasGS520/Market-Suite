""" Métricas Prometheus para auditoria de logs de scraping """

import os

# Importa métricas apropriadas baseado em ENABLE_METRICS
_ENABLE_METRICS = os.getenv("ENABLE_METRICS", "0") in {"1", "true", "True", "yes"}
if _ENABLE_METRICS:
    from prometheus_client import Counter, Histogram
else:
    from shared.metrics_noop import Counter, Histogram

AUDIT_RECORDS_TOTAL = Counter(
    "audit_records_total",
    "Total de registros de auditoria gerados",
    ["stage"],
)

AUDIT_HTML_LENGTH_BYTES = Histogram(
    "audit_html_length_bytes",
    "Tamanho em bytes do HTML registrado na auditoria",
    ["stage"],
    buckets=[0, 256, 1024, 4096, 16384, 65536, 262144],
)

AUDIT_RECORD_DURATION_SECONDS = Histogram(
    "audit_record_duration_seconds",
    "Tempo gasto para gravar cada registro de auditoria (segundos)",
    ["stage"],
    buckets=[0.0001, 0.001, 0.005, 0.01, 0.05, 0.1, 0.5, 1.0],
)

AUDIT_ERRORS_TOTAL = Counter(
    "audit_errors_total",
    "Total de erros ao gravar registros de auditoria",
    ["stage"],
)

__all__ = [
    "AUDIT_RECORDS_TOTAL",
    "AUDIT_HTML_LENGTH_BYTES",
    "AUDIT_RECORD_DURATION_SECONDS",
    "AUDIT_ERRORS_TOTAL",
]
