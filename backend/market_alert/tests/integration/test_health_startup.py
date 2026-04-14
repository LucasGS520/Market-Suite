""" Testes de integração controlada para health e readiness. """

from __future__ import annotations

import sys
from types import SimpleNamespace

import pytest

from market_alert.infrastructure.routes import routes_health


pytestmark = pytest.mark.integration


class _OkConnection:
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def execute(self, statement):
        return 1


class _OkEngine:
    def connect(self):
        return _OkConnection()


class _RedisOk:
    def ping(self):
        return True

    def get(self, key):
        return None


class _RedisUnavailable:
    def ping(self):
        raise RuntimeError("redis down")


def test_health_endpoint_reports_partial_failure_when_beat_is_missing(monkeypatch, api_client) -> None:
    monkeypatch.setattr(routes_health, "get_engine", lambda: _OkEngine())
    monkeypatch.setattr(routes_health.redis, "from_url", lambda url: _RedisOk())
    monkeypatch.setattr(routes_health, "get_redis_metrics", lambda: {"queues": 0})
    monkeypatch.setitem(
        sys.modules,
        "shared.clients.temporal.orchestrator_client",
        SimpleNamespace(get_temporal_client=lambda: SimpleNamespace(probe_connectivity_sync=lambda: True)),
    )

    response = api_client.get("/health/")

    assert response.status_code == 200
    body = response.json()
    assert body["postgres"]["status"] == "ok"
    assert body["redis"]["status"] == "ok"
    assert body["beat"]["status"] == "missing"
    assert body["overall"] == "error"


def test_readiness_returns_503_when_redis_is_unavailable(monkeypatch, api_client) -> None:
    monkeypatch.setattr(routes_health, "get_engine", lambda: _OkEngine())
    monkeypatch.setattr(routes_health.redis, "from_url", lambda url: _RedisUnavailable())

    response = api_client.get("/health/readiness")

    assert response.status_code == 503
    body = response.json()["detail"]
    assert body["postgres"]["status"] == "ok"
    assert body["redis"]["status"] == "error"


# ---------------------------------------------------------------------------
# Thresholds de degraded — Fase 3 (hardening operacional)
# ---------------------------------------------------------------------------

def _ok_beat_redis() -> _RedisOk:
    """Redis stub que retorna heartbeat válido de beat para evitar `beat.status=missing`."""
    from datetime import datetime, timezone

    class _BeatRedis(_RedisOk):
        def get(self, key):
            if "beat:last_success" in key:
                return datetime.now(timezone.utc).isoformat().encode()
            return None

    return _BeatRedis()


def test_health_degraded_when_dlq_has_backlog(monkeypatch, api_client) -> None:
    """DLQ com tasks em falha permanente deve degradar o status geral."""
    monkeypatch.setattr(routes_health, "get_engine", lambda: _OkEngine())
    monkeypatch.setattr(routes_health.redis, "from_url", lambda url: _ok_beat_redis())
    monkeypatch.setattr(routes_health, "get_redis_metrics", lambda: {
        "dlq_backlog": 3,
        "queue_processing": 0,
        "celery_queue_scraping": 0,
    })
    monkeypatch.setitem(
        sys.modules,
        "shared.clients.temporal.orchestrator_client",
        SimpleNamespace(get_temporal_client=lambda: SimpleNamespace(probe_connectivity_sync=lambda: True)),
    )

    response = api_client.get("/health/")

    assert response.status_code == 200
    body = response.json()
    assert body["overall"] == "degraded"
    assert body["coordination"]["status"] == "degraded"
    assert "3" in body["coordination"]["detail"]


def test_health_degraded_when_queue_processing_is_saturated(monkeypatch, api_client) -> None:
    """queue_processing acima do limiar (>20) deve degradar o status geral."""
    monkeypatch.setattr(routes_health, "get_engine", lambda: _OkEngine())
    monkeypatch.setattr(routes_health.redis, "from_url", lambda url: _ok_beat_redis())
    monkeypatch.setattr(routes_health, "get_redis_metrics", lambda: {
        "dlq_backlog": 0,
        "queue_processing": 25,
        "celery_queue_scraping": 0,
    })
    monkeypatch.setitem(
        sys.modules,
        "shared.clients.temporal.orchestrator_client",
        SimpleNamespace(get_temporal_client=lambda: SimpleNamespace(probe_connectivity_sync=lambda: True)),
    )

    response = api_client.get("/health/")

    assert response.status_code == 200
    body = response.json()
    assert body["overall"] == "degraded"
    assert body["coordination"]["queue_processing_high"] == 25


def test_health_degraded_when_scraping_queue_has_deep_backlog(monkeypatch, api_client) -> None:
    """Fila de scraping com backlog alto (>50) deve degradar o status geral."""
    monkeypatch.setattr(routes_health, "get_engine", lambda: _OkEngine())
    monkeypatch.setattr(routes_health.redis, "from_url", lambda url: _ok_beat_redis())
    monkeypatch.setattr(routes_health, "get_redis_metrics", lambda: {
        "dlq_backlog": 0,
        "queue_processing": 5,
        "celery_queue_scraping": 75,
    })
    monkeypatch.setitem(
        sys.modules,
        "shared.clients.temporal.orchestrator_client",
        SimpleNamespace(get_temporal_client=lambda: SimpleNamespace(probe_connectivity_sync=lambda: True)),
    )

    response = api_client.get("/health/")

    assert response.status_code == 200
    body = response.json()
    assert body["overall"] == "degraded"
    assert body["coordination"]["scraping_queue_backlog"] == 75


def test_health_ok_when_all_thresholds_are_below_limits(monkeypatch, api_client) -> None:
    """Métricas abaixo dos limiares não devem degradar o status."""
    monkeypatch.setattr(routes_health, "get_engine", lambda: _OkEngine())
    monkeypatch.setattr(routes_health.redis, "from_url", lambda url: _ok_beat_redis())
    monkeypatch.setattr(routes_health, "get_redis_metrics", lambda: {
        "dlq_backlog": 0,
        "queue_processing": 10,
        "celery_queue_scraping": 20,
    })
    monkeypatch.setitem(
        sys.modules,
        "shared.clients.temporal.orchestrator_client",
        SimpleNamespace(get_temporal_client=lambda: SimpleNamespace(probe_connectivity_sync=lambda: True)),
    )

    response = api_client.get("/health/")

    assert response.status_code == 200
    body = response.json()
    assert body["overall"] == "ok"
    assert "coordination" not in body
