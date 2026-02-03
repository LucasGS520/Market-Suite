""" Implementações no-op para métricas Prometheus

Este módulo fornece implementações stub das classes de métricas do
prometheus_client que não fazem nada (no-op), permitindo que o código
continue funcionando sem coletar métricas reais.

Todas as interfaces públicas (Counter, Gauge, Histogram, Summary) e
métodos (.inc(), .dec(), .observe(), .set(), .labels(), etc.) são
preservadas para manter compatibilidade.
"""

from typing import Any, Optional, Dict, List
from contextlib import contextmanager


class _NoOpMetric:
    """ Base para métricas no-op que implementa interface comum """

    def __init__(self, name: str, documentation: str, labelnames: Optional[List[str]] = None, *args, **kwargs):
        """ Aceita todos os argumentos do prometheus_client mas ignora """
        self._name = name
        self._documentation = documentation
        self._labelnames = labelnames or []

    def labels(self, *args, **kwargs):
        """ Retorna self para permitir chaining: metric.labels(x=1).inc() """
        return self

    def __call__(self, *args, **kwargs):
        """ Permite uso como decorador """
        def decorator(func):
            return func
        return decorator


class Counter(_NoOpMetric):
    """ Stub no-op para prometheus_client.Counter """

    def inc(self, amount: float = 1):
        """ Não faz nada """
        pass

    def count_exceptions(self, exception=Exception):
        """ Retorna context manager no-op """
        @contextmanager
        def _noop_context():
            yield
        return _noop_context()


class Gauge(_NoOpMetric):
    """ Stub no-op para prometheus_client.Gauge """

    def inc(self, amount: float = 1):
        """ Não faz nada """
        pass

    def dec(self, amount: float = 1):
        """ Não faz nada """
        pass

    def set(self, value: float):
        """ Não faz nada """
        pass

    def set_to_current_time(self):
        """ Não faz nada """
        pass

    @contextmanager
    def track_inprogress(self):
        """ Context manager no-op """
        yield

    def time(self):
        """ Retorna context manager no-op para medir tempo """
        @contextmanager
        def _noop_timer():
            yield
        return _noop_timer()


class Histogram(_NoOpMetric):
    """ Stub no-op para prometheus_client.Histogram """

    def observe(self, amount: float):
        """ Não faz nada """
        pass

    def time(self):
        """ Retorna context manager no-op para medir tempo """
        @contextmanager
        def _noop_timer():
            yield
        return _noop_timer()


class Summary(_NoOpMetric):
    """ Stub no-op para prometheus_client.Summary """

    def observe(self, amount: float):
        """ Não faz nada """
        pass

    def time(self):
        """ Retorna context manager no-op para medir tempo """
        @contextmanager
        def _noop_timer():
            yield
        return _noop_timer()


class Info(_NoOpMetric):
    """ Stub no-op para prometheus_client.Info """

    def info(self, val: Dict[str, str]):
        """ Não faz nada """
        pass


class Enum(_NoOpMetric):
    """ Stub no-op para prometheus_client.Enum """

    def state(self, state: str):
        """ Não faz nada """
        pass


# Stubs para registry e funções auxiliares
class _NoOpCollectorRegistry:
    """ Registry no-op """

    def register(self, collector):
        pass

    def unregister(self, collector):
        pass

    def collect(self):
        return []

    def get_sample_value(self, name, labels=None):
        return None


REGISTRY = _NoOpCollectorRegistry()
CollectorRegistry = _NoOpCollectorRegistry


def generate_latest(registry=None):
    """ Retorna payload vazio para endpoint /metrics """
    return b""


def start_http_server(port: int, addr: str = "0.0.0.0", registry=None):
    """ Não inicia servidor HTTP """
    pass


CONTENT_TYPE_LATEST = "text/plain; version=0.0.4; charset=utf-8"


__all__ = [
    "Counter",
    "Gauge",
    "Histogram",
    "Summary",
    "Info",
    "Enum",
    "REGISTRY",
    "CollectorRegistry",
    "generate_latest",
    "start_http_server",
    "CONTENT_TYPE_LATEST",
]
