""" Testes de integração controlada para endpoint temporal. """

from __future__ import annotations

import sys
from types import SimpleNamespace

import pytest


pytestmark = [pytest.mark.integration, pytest.mark.integration_high_cost]


def test_temporal_health_endpoint_returns_healthy_with_controlled_probe(
    monkeypatch,
    api_client,
) -> None:
    fake_temporal_module = SimpleNamespace(
        get_temporal_client=lambda: SimpleNamespace(probe_connectivity_sync=lambda: True),
        get_temporal_connection_info=lambda: {
            "namespace": "default",
            "task_queue": "market-alert",
        },
    )
    monkeypatch.setitem(
        sys.modules,
        "shared.clients.temporal.orchestrator_client",
        fake_temporal_module,
    )

    response = api_client.get("/health/temporal")

    assert response.status_code == 200
    assert response.json()["status"] == "healthy"
    assert response.json()["temporal_connected"] is True
