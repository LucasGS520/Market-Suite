""" Stubs no-op para prometheus_client

Este módulo fornece stubs que imitam o prometheus_client quando
a observabilidade está desabilitada, evitando dependência externa.
"""

# Stub para REGISTRY
class _NoOpRegistry:
    """ Stub do REGISTRY do Prometheus """
    pass

REGISTRY = _NoOpRegistry()

# Constantes
CONTENT_TYPE_LATEST = "text/plain; version=0.0.4; charset=utf-8"

def generate_latest(registry=None):
    """ Gera payload vazio de métricas (no-op) """
    return b""

def start_http_server(port, addr="0.0.0.0", registry=None):
    """ Inicia servidor HTTP no-op (não faz nada) """
    pass

__all__ = [
    "REGISTRY",
    "CONTENT_TYPE_LATEST", 
    "generate_latest",
    "start_http_server",
]
