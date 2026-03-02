""" Pontos de entrada Celery do domínio de coletores 

A exportação explícita evita depender da descoberta implícita de submódulos e
mantém uma API clara para tarefas assíncronas compartilhadas.
"""

from market_alert.collectors.tasks import (
    collector_product_task,
    continuous_collector_task,
    priority_queue_tasks,
)

__all__ = ["collector_product_task", "continuous_collector_task", "priority_queue_tasks"]
