""" Catálogo de filas, rotas e agendamentos do worker Celery.

Centraliza as declarações para evitar divergências entre arquivos de
configuração e garantir que novas tasks fiquem visíveis para operação.
Qualquer fila ou agendamento deve ser registrado aqui.

Responsabilidade única:
    Definir TASK_MODULES, exchanges, filas, rotas e beat schedules.
    Nenhuma lógica de negócio ou inicialização de workers aqui.
"""

from __future__ import annotations

from celery.schedules import crontab
from kombu import Exchange, Queue


#Módulos de tasks carregados pelo worker
TASK_MODULES = [
    "market_alert.collectors.tasks.collector_product_task",
    "market_alert.comparisons.tasks.compare_prices_task",
    "market_alert.notifications.tasks.notifications_enqueue_task",
    "market_alert.notifications.tasks.send_notification_task",
    "market_alert.users.tasks.verification_tasks",
    "market_alert.infraestructure.tasks.maintenance_tasks",
]

#Exchanges separados por domínio funcional (3 workers: scraping, compare, notifications)
SCRAPING_EXCHANGE = Exchange("scraping", type="direct")
COMPARE_EXCHANGE = Exchange("compare", type="direct")
NOTIFICATIONS_EXCHANGE = Exchange("notifications", type="direct")

#Filas conhecidas do serviço
TASK_QUEUES = (
    Queue("scraping", SCRAPING_EXCHANGE, routing_key="scraping"),
    Queue("compare", COMPARE_EXCHANGE, routing_key="compare"),
    Queue("notifications", NOTIFICATIONS_EXCHANGE, routing_key="notifications"),
)

#Roteamento explícito para manter cada domínio em sua fila
TASK_ROUTES = {
    "market_alert.collectors.tasks.collector_product_task.collect_product_task": {
        "queue": "scraping",
        "routing_key": "scraping",
    },
    "market_alert.comparisons.tasks.compare_prices_task.compare_prices_task": {
        "queue": "compare",
        "routing_key": "compare",
    },
    "market_alert.notifications.tasks.notifications_enqueue_task.enqueue_notifications_task": {
        "queue": "notifications",
        "routing_key": "notifications",
    },
    "market_alert.notifications.tasks.send_notification_task.send_notification_task": {
        "queue": "notifications",
        "routing_key": "notifications",
    },
    "market_alert.users.tasks.verification_tasks.send_email_verification": {
        "queue": "notifications",
        "routing_key": "notifications",
    },
    "market_alert.users.tasks.verification_tasks.send_phone_otp": {
        "queue": "notifications",
        "routing_key": "notifications",
    },
}

def _schedule_entry(
    task: str,
    schedule,
    *,
    queue: str = "maintenance",
    routing_key: str | None = None,
) -> dict:
    """ Cria uma entrada de agendamento consistente para o Beat. """
    return {
        "task": task,
        "schedule": schedule,
        "options": {"queue": queue, "routing_key": routing_key or queue},
    }

#Agendamentos periódicos (Celery Beat)
#Mantidos aqui para simplificar auditoria e evitar divergências
BEAT_SCHEDULE = {
    "cleanup-cache-daily": _schedule_entry(
        "market_alert.infraestructure.tasks.maintenance_tasks.cleanup_cache",
        crontab(hour=3, minute=0),
        queue="scraping",
    ),
}


__all__ = [
    "TASK_MODULES",
    "TASK_QUEUES",
    "TASK_ROUTES",
    "BEAT_SCHEDULE",
]
