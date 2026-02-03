""" Implementações no-op (stub) de métricas Prometheus

Este módulo fornece classes stub que imitam a API do prometheus_client,
mas não executam nenhuma operação real de coleta ou exposição de métricas.
Usado quando ENABLE_METRICS=0 para evitar overhead de observabilidade.
"""


class NoOpMetric:
    """ Métrica base no-op que ignora todas as operações """
    
    def __init__(self, name, documentation, labelnames=None, **kwargs):
        """ Inicializa métrica stub sem operações reais """
        self.name = name
        self.documentation = documentation
        self.labelnames = labelnames or []
        self._kwargs = kwargs
    
    def labels(self, *args, **kwargs):
        """ Retorna self para permitir chamadas encadeadas """
        return self
    
    def inc(self, amount=1):
        """ No-op para incremento """
        pass
    
    def dec(self, amount=1):
        """ No-op para decremento """
        pass
    
    def set(self, value):
        """ No-op para definir valor """
        pass
    
    def observe(self, value):
        """ No-op para observar valor """
        pass
    
    def time(self):
        """ Retorna context manager no-op para medição de tempo """
        return NoOpTimer()


class NoOpTimer:
    """ Context manager no-op para medições de tempo """
    
    def __enter__(self):
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        pass


class Counter(NoOpMetric):
    """ Stub de Counter do Prometheus """
    pass


class Gauge(NoOpMetric):
    """ Stub de Gauge do Prometheus """
    pass


class Histogram(NoOpMetric):
    """ Stub de Histogram do Prometheus """
    pass


class Summary(NoOpMetric):
    """ Stub de Summary do Prometheus """
    pass


__all__ = ["Counter", "Gauge", "Histogram", "Summary", "NoOpMetric", "NoOpTimer"]
