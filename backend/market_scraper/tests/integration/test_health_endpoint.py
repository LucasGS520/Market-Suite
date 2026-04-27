from __future__ import annotations


def test_health_endpoint_returns_service_ok(integration_client):
    response = integration_client.get("/health/ping")

    assert response.status_code == 200
    assert response.json()["status"] == "ok"
