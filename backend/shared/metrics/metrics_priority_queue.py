""" Métricas para o agendamento contínuo via fila de prioridade """

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
    labelnames=("source", "outcome"),
)

PRIORITY_QUEUE_LOOP_ERRORS_TOTAL = Counter(
    "priority_queue_loop_errors_total",
    "Total de erros capturados no loop do worker contínuo",
    labelnames=("source",),
)

CONTINUOUS_COLLECTOR_SOFT_TIMEOUTS_TOTAL = Counter(
    "continuous_collector_soft_timeouts_total",
    "Total de timeouts suaves capturados no loop do coletor contínuo",
)

CONTINUOUS_COLLECTOR_TIME_LIMIT_EXCEEDED_TOTAL = Counter(
    "continuous_collector_time_limit_exceeded_total",
    "Total de limites de tempo excedidos no coletor contínuo",
)

PRIORITY_QUEUE_RECONCILE_TRIGGERED_TOTAL = Counter(
    "priority_queue_reconcile_triggered_total",
    "Total de reconciliações disparadas para a fila de prioridade",
    labelnames=("source","reason"),
)
PRIORITY_QUEUE_FAILED_BUT_RETAINED_TOTAL = Counter(
    "priority_queue_failed_but_retained_total",
    "Total de reenqueues que falharam e ficaram retidos no processamento",
    labelnames=("source",),
)

PRIORITY_QUEUE_PENDING_REQUEUE_TOTAL = Counter(
    "priority_queue_pending_requeue_total",
    "Total de itens mantidos no processamento aguardando requeue pós-coleta",
    labelnames=("source",),
)

PRIORITY_QUEUE_REQUEUED_FROM_PROCESSING_TOTAL = Counter(
    "priority_queue_requeued_from_processing_total",
    "Total de itens que retornaram do processamento para a fila ready",
    labelnames=("source", "reason"),
)

__all__ = [
    "PRIORITY_QUEUE_SIZE",
    "PRIORITY_QUEUE_READY_TOTAL",
    "PRIORITY_QUEUE_CONSUME_LATENCY_MS",
    "PRIORITY_QUEUE_STABILITY_TOTAL",
    "PRIORITY_QUEUE_ENQUEUED_TOTAL",
    "PRIORITY_QUEUE_FALLBACK_TOTAL",
    "PRIORITY_QUEUE_PROCESSED_TOTAL",
    "PRIORITY_QUEUE_LOOP_ERRORS_TOTAL",
    "CONTINUOUS_COLLECTOR_SOFT_TIMEOUTS_TOTAL",
    "CONTINUOUS_COLLECTOR_TIME_LIMIT_EXCEEDED_TOTAL",
    "PRIORITY_QUEUE_RECONCILE_TRIGGERED_TOTAL",
    "PRIORITY_QUEUE_FAILED_BUT_RETAINED_TOTAL",
    "PRIORITY_QUEUE_PENDING_REQUEUE_TOTAL",
    "PRIORITY_QUEUE_REQUEUED_FROM_PROCESSING_TOTAL",
]
