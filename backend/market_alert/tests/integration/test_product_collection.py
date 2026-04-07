""" Testes de integração controlada para fluxo de monitoramento. """

from __future__ import annotations

from copy import deepcopy
from datetime import timedelta
from uuid import uuid4

import pytest

from market_alert.products.routes import routes_monitored


pytestmark = pytest.mark.integration


def test_product_collection_flow_create_list_pause_and_get(
    monkeypatch,
    api_client,
    integration_state,
    monitored_product_payload,
    integration_now,
    integration_current_user,
) -> None:
    monitored = deepcopy(monitored_product_payload)
    monitored["owner_id"] = integration_current_user.id
    monitored["id"] = uuid4()
    monitored["url"] = "https://store.example.com/products/phase4-monitorado"
    monitored["normalized_url"] = monitored["url"]
    monitored["created_at"] = integration_now
    monitored["monitored_since"] = integration_now
    monitored["next_check_at"] = integration_now + timedelta(minutes=15)
    monitored["last_scraped_at"] = integration_now
    monitored["last_collected_at"] = integration_now

    def _create_monitored_product(db, user, product_data, request):
        integration_state["monitored"][str(monitored["id"])] = dict(monitored)
        return {
            "id": monitored["id"],
            "url": monitored["url"],
            "created_at": monitored["created_at"],
            "next_check_at": monitored["next_check_at"],
            "message": "Monitoramento agendado",
            "competitor_warning": None,
        }

    def _list_monitored_products_service(db, user_id, page, per_page, query, status):
        return {
            "items": list(integration_state["monitored"].values()),
            "meta": {
                "total": len(integration_state["monitored"]),
                "page": page,
                "per_page": per_page or len(integration_state["monitored"]) or 1,
            },
        }

    def _get_monitored_product(db, product_id, user_id):
        return integration_state["monitored"][str(product_id)]

    def _update_monitored_pause_state(db, product_id, user, payload):
        persisted = integration_state["monitored"][str(product_id)]
        persisted["paused"] = payload.paused
        persisted["display_status"] = "paused" if payload.paused else "competitive"
        return persisted

    monkeypatch.setattr(routes_monitored, "create_monitored_product", _create_monitored_product)
    monkeypatch.setattr(routes_monitored, "list_monitored_products_service", _list_monitored_products_service)
    monkeypatch.setattr(routes_monitored, "get_monitored_product", _get_monitored_product)
    monkeypatch.setattr(routes_monitored, "update_monitored_pause_state", _update_monitored_pause_state)

    create_response = api_client.post(
        "/monitored/scrape",
        json={
            "name_identification": monitored["name"],
            "product_url": monitored["url"],
        },
        headers={"Authorization": "Bearer test-access-token"},
    )
    assert create_response.status_code == 202
    assert create_response.json()["message"] == "Monitoramento agendado"

    list_response = api_client.get("/monitored/", headers={"Authorization": "Bearer test-access-token"})
    assert list_response.status_code == 200
    assert list_response.json()["meta"]["total"] == 1
    assert list_response.json()["items"][0]["id"] == str(monitored["id"])

    pause_response = api_client.put(
        f"/monitored/{monitored['id']}/paused",
        params={"paused": "true"},
        headers={"Authorization": "Bearer test-access-token"},
    )
    assert pause_response.status_code == 200
    assert pause_response.json()["paused"] is True
    assert pause_response.json()["display_status"] == "paused"

    get_response = api_client.get(
        f"/monitored/{monitored['id']}",
        headers={"Authorization": "Bearer test-access-token"},
    )
    assert get_response.status_code == 200
    assert get_response.json()["paused"] is True
