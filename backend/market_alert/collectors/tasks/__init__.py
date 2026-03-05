""" Pontos de entrada Celery do domínio de coletores 

Este pacote evita importações imediatas de submódulos para reduzir o risco de
circular dependency e falhas de bootstrap durante a inicialização do processo.
A API pública mantém compatibilidade por meio de ``__getattr__``.
"""

from __future__ import annotations

from importlib import import_module

# Mapeia nomes públicos para seus submódulos e permite lazy loading controlado.
_LAZY_SUBMODULES = {
    "collector_product_task": "market_alert.collectors.tasks.collector_product_task",
    "continuous_collector_task": "market_alert.collectors.tasks.continuous_collector_task",
    "priority_queue_tasks": "market_alert.collectors.tasks.priority_queue_tasks",
}

__all__ = list(_LAZY_SUBMODULES)


def __getattr__(name: str):
    """Resolve submódulos sob demanda para manter compatibilidade de import."""
    module_path = _LAZY_SUBMODULES.get(name)
    if module_path is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    module = import_module(module_path)
    globals()[name] = module
    return module
