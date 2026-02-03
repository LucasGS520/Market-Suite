""" Métricas Prometheus para tarefas e workers do Celery

Este módulo agrupa contadores, gauges e histogramas
relacionados ao processamento assíncrono executado pelo
Celery, permitindo observar volume de tarefas, tamanho
das filas e duração das execuções.
"""

from ._noop_metrics import Counter, Gauge, Histogram

CELERY_TASKS_TOTAL = Counter(
    "celery_tasks_total",
    "Total de tarefas executadas pelo Celery",
    ["service", "task_name", "status"],
)

CELERY_QUEUE_LENGTH = Gauge(
    "celery_queue_length",
    "Número de tarefas pendentes na fila Celery",
    ["service", "queue"],
)

CELERY_WORKERS_TOTAL = Gauge(
    "celery_workers_total",
    "Total de workers Celery ativos",
    ["service"],
)

CELERY_WORKER_CONCURRENCY = Gauge(
    "celery_worker_concurrency",
    "Grau de concorrência configurado nos workers Celery",
    ["service"],
)

CELERY_TASK_DURATION_SECONDS = Histogram(
    "celery_task_duration_seconds",
    "Tempo de execução de cada tarefa celery (segundos)",
    ["service", "task_name"],
    buckets=[0.001, 0.005, 0.01, 0.05, 0.1, 0.5, 1.0, 2.5, 5.0, 10.0],
)

CELERY_CONTINUOUS_AUTOSTART_TOTAL = Counter(
    "celery_continuous_autostart_total",
    "Total de reativações ou disparos do autostart do coletor contínuo",
    ["service", "action"],
)

CONTINUOUS_AUTOSTART_THROTTLED_TOTAL = Counter(
    "continuous_autostart_throttled_total",
    "Total de bloqueios de autostart do coletor contínuo por throttling",
    ["service", "reason"],
)

__all__ = [
    "CELERY_TASKS_TOTAL",
    "CELERY_QUEUE_LENGTH",
    "CELERY_WORKERS_TOTAL",
    "CELERY_WORKER_CONCURRENCY",
    "CELERY_TASK_DURATION_SECONDS",
    "CELERY_CONTINUOUS_AUTOSTART_TOTAL",
    "CONTINUOUS_AUTOSTART_THROTTLED_TOTAL",
]
