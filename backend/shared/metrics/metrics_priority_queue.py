""" Metricas para o agendamento contínuo via fila de prioridade """

from prometheus_client import Counter, Gauge, Histogram

PRIORITY_QUEUE_SIZE = Gauge(
    "priority_queue_size",
    "Quantidade atual de itens na fila de prioridade",
)

PRIORITY_QUEUE_READY_TOTAL = Gauge(
    "priority_queue_ready_total",
    "Quantidade de itens prontos para coleta na fila de prioridade",
)

PRIORITY_QUEUE_CONSUME_LATENCY_MS = Histogram(
    "priority_queue_consume_latency_ms",
    "Latência em milissegundos entre enfileiramento e consumo",
    buckets=(50, 100, 250, 500, 1000, 2000, 5000, 10000, 30000),
)

PRIORITY_QUEUE_STABILITY_TOTAL = Gauge(
    "priority_queue_products_by_stability",
    "Quantidade de produtos por faixa de estabilidade",
    labelnames=("stability",),
)

PRIORITY_QUEUE_ENQUEUED_TOTAL = Counter(
    "priority_queue_enqueued_total",
    "Total de itens enfileirados na fila de prioridade",
    labelnames=("source",),
)

PRIORITY_QUEUE_FALLBACK_TOTAL = Counter(
    "priority_queue_fallback_total",
    "Total de enfileiramentos enviados via fallback Celery",
    labelnames=("source",),
)

PRIORITY_QUEUE_PROCESSED_TOTAL = Counter(
    "priority_queue_processed_total",
    "Total de itens processados pelo worker contínuo",
    labelnames=("source",),
)

__all__ = [
    "PRIORITY_QUEUE_SIZE",
    "PRIORITY_QUEUE_READY_TOTAL",
    "PRIORITY_QUEUE_CONSUME_LATENCY_MS",
    "PRIORITY_QUEUE_STABILITY_TOTAL",
    "PRIORITY_QUEUE_ENQUEUED_TOTAL",
    "PRIORITY_QUEUE_FALLBACK_TOTAL",
    "PRIORITY_QUEUE_PROCESSED_TOTAL",
]
