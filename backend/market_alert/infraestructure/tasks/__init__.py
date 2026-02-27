""" Tasks técnicas da camada de infraestrutura 

Exporta apenas tarefas operacionais estáveis para manutenção do ambiente.
"""

from market_alert.infraestructure.tasks.maintenance_tasks import cleanup_cache

__all__ = ["cleanup_cache"]
