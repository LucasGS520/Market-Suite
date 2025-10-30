""" Exposição controlada dos utilitários do serviço de scraping """

import importlib
from types import ModuleType

__all__ = ["url_validation"]


def __getattr__(name: str) -> ModuleType:
    """ Carrega módulos sob demanda para evitar ciclos de importação """
    if name in __all__:
        module = importlib.import_module(f"{__name__}.{name}")
        globals()[name] = module
        return module
    raise AttributeError(f"módulo {name!r} não encontrado em market_scraper.utils")
