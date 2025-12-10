""" Catálogo de filas, rotas e agendamentos do worker Celery.

Centralizamos as declarações para evitar divergências entre arquivos de
configuração e garantir que novas tasks fiquem visíveis para operação.
Qualquer fila ou agendamento deve ser registrado aqui.
"""

from __future__ import annotations

from celery.schedules import crontab
from kombu import Exchange, Queue


#Módulos de tasks carregados pelo worker
TASK_MODULES = [
    "market_alert.tasks.collector_product_task",
    "market_alert.tasks.metrics_tasks",
    "market_alert.tasks.compare_prices_task",
    "market_alert.tasks.alert_tasks",
    "market_alert.tasks.monitor_recheck_tasks",
]

#Exchanges separados para scraping e monitoramento
SCRAPING_EXCHANGE = Exchange("scraping", type="direct")
MONITOR_EXCHANGE = Exchange("monitor", type="direct")

#Filas conhecidas do serviço
TASK_QUEUES = (
    Queue("scraping", SCRAPING_EXCHANGE, routing_key="scraping"),
    Queue("monitor", MONITOR_EXCHANGE, routing_key="monitor"),
)

#Roteamento explícito para manter cada domínio em sua fila
TASK_ROUTES = {
    "market_alert.tasks.collector_product_task.collect_product_task": {
        "queue": "scraping",
        "routing_key": "scraping",
    },
    "market_alert.tasks.monitor_recheck_tasks.enqueue_due_monitored": {
        "queue": "monitor",
        "routing_key": "monitor",
    },
    "market_alert.tasks.monitor_recheck_tasks.recheck_monitored_product": {
        "queue": "monitor",
        "routing_key": "monitor",
    },
}


def _schedule_entry(task: str, schedule, *, queue: str = "monitor", routing_key: str | None = None) -> dict:
    """Cria uma entrada de agendamento consistente para o Beat."""
    return {
        "task": task,
        "schedule": schedule,
        "options": {"queue": queue, "routing_key": routing_key or queue},
    }


#Agendamentos periódicos (Celery Beat)
#Mantidos aqui para simplificar auditoria e evitar divergências
BEAT_SCHEDULE = {
    "collect-celery-metrics-every-1min": _schedule_entry(
        "market_alert.tasks.metrics_tasks.collect_celery_metrics",
        crontab(minute="*/1"),
    ),
    "collect-audit-metrics-every-1min": _schedule_entry(
        "market_alert.tasks.metrics_tasks.collect_audit_metrics",
        crontab(minute="*/1"),
    ),
    "collect-db-metrics-every-1min": _schedule_entry(
        "market_alert.tasks.metrics_tasks.collect_db_metrics",
        crontab(minute="*/1"),
    ),
    "recheck-scraping-every-5min": _schedule_entry(
        "market_alert.tasks.monitor_recheck_tasks.enqueue_due_monitored",
        crontab(minute="*/5"),
        queue="monitor",
        routing_key="monitor",
    ),
    "cleanup-cache-daily": _schedule_entry(
        "market_alert.tasks.metrics_tasks.cleanup_cache",
        crontab(hour=3, minute=0),
    ),
}


__all__ = [
    "TASK_MODULES",
    "TASK_QUEUES",
    "TASK_ROUTES",
    "BEAT_SCHEDULE",
]
