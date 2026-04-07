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
