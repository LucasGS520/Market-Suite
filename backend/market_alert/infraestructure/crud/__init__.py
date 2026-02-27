""" Persistência de suporte ao ciclo de execução do Celery 

Reúne operações de armazenamento voltadas à observabilidade operacional,
como registro de falhas permanentes de tasks.
"""

from market_alert.infraestructure.crud.crud_task_failures import create_task_failure

__all__ = ["create_task_failure"]
