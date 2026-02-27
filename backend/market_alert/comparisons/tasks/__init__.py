"""Facade de tarefas assíncronas do módulo de comparações.

Mantém um ponto único para importar tasks públicas usadas pelo Celery.
"""

from market_alert.comparisons.tasks.compare_prices_task import compare_prices_task

__all__ = ["compare_prices_task"]
