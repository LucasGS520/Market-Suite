""" Testes para validação das métricas Prometheus """

from prometheus_client import REGISTRY

from shared.metrics.metrics_http import HTTP_REQUESTS_TOTAL
from shared.metrics.metrics_scraper import SCRAPER_CACHE_LOOKUPS_TOTAL

def test_http_requests_total_increment():
    HTTP_REQUESTS_TOTAL.clear()

    labels = {
        "service": "test_service",
        "method": "GET",
        "endpoint": "/teste",
        "status_code": "200",
    }
    valor_inicial = REGISTRY.get_sample_value("http_requests_total", labels)
    assert valor_inicial is None

    HTTP_REQUESTS_TOTAL.labels(**labels).inc()

    valor_final = REGISTRY.get_sample_value("http_requests_total", labels)
    assert valor_final == 1.0

def test_scraper_cache_lookups_total_increment():
    SCRAPER_CACHE_LOOKUPS_TOTAL.clear()

    valor_inicial = REGISTRY.get_sample_value(
        "scraper_cache_lookups_total",
        {"outcome": "hit"},
    )
    assert valor_inicial is None

    SCRAPER_CACHE_LOOKUPS_TOTAL.labels(outcome="hit").inc()

    valor_final = REGISTRY.get_sample_value(
        "scraper_cache_lookups_total",
        {"outcome": "hit"},
    )
    assert valor_final == 1.0
