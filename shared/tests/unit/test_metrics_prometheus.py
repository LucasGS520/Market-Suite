""" Testes para validação das métricas Prometheus """

from prometheus_client import REGISTRY

from shared.metrics.metrics_http import HTTP_REQUESTS_TOTAL
from shared.metrics.metrics_scraper import SCRAPER_REQUESTS_TOTAL

def test_http_requests_total_increment():
    HTTP_REQUESTS_TOTAL.clear()

    valor_inicial = REGISTRY.get_sample_value(
        "http_requests_total",
        {"method": "GET", "endpoint": "/teste", "status_code": "200"},
    )
    assert valor_inicial is None

    HTTP_REQUESTS_TOTAL.labels(method="GET", endpoint="/teste", status_code=200).inc()

    valor_final = REGISTRY.get_sample_value(
        "http_requests_total",
        {"method": "GET", "endpoint": "/teste", "status_code": "200"},
    )
    assert valor_final == 1.0

def test_scraper_requests_total_increment():
    SCRAPER_REQUESTS_TOTAL.clear()

    valor_inicial = REGISTRY.get_sample_value(
        "scraper_requests_total",
        {"method": "GET", "status_code": "200"},
    )
    assert valor_inicial is None

    SCRAPER_REQUESTS_TOTAL.labels(method="GET", status_code=200).inc()

    valor_final = REGISTRY.get_sample_value(
        "scraper_requests_total",
        {"method": "GET", "status_code": "200"},
    )
    assert valor_final == 1.0
