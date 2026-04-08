""" Testes de integração controlada para dashboard e concorrentes. """

from __future__ import annotations

from copy import deepcopy
from types import SimpleNamespace
from uuid import uuid4

import pytest

from market_alert.products.routes import routes_competitors, routes_dashboard
from market_alert.schemas.schemas_products import CompetitorsListResponse


pytestmark = pytest.mark.integration


def test_dashboard_stats_http_contract(monkeypatch, api_client) -> None:
    monkeypatch.setattr(
        routes_dashboard,
        "gather_dashboard_totals",
        lambda db, user: {
            "monitored_total": 3,
            "competitors_total": 5,
            "alerts_total": 2,
            "notifications_pending": 1,
        },
    )

    response = api_client.get("/dashboard/stats", headers={"Authorization": "Bearer test-access-token"})

    assert response.status_code == 200
    assert response.json() == {
        "monitored_total": 3,
        "competitors_total": 5,
        "alerts_total": 2,
        "notifications_pending": 1,
    }


def test_competitors_scrape_and_list_http_contract(
    monkeypatch,
    api_client,
    monitored_product_payload,
    competitor_product_payload,
    integration_now,
) -> None:
    monitored = deepcopy(monitored_product_payload)
    monitored_id = monitored["id"]
    competitor = deepcopy(competitor_product_payload)
    competitor["id"] = uuid4()
    competitor["monitored_product_id"] = monitored_id

    monkeypatch.setattr(
        routes_competitors,
        "create_competitor_scrape_request",
        lambda db, user, product_data, request_context: SimpleNamespace(
            id=competitor["id"],
            url=competitor["url"],
            created_at=integration_now,
            message="Concorrente agendado",
        ),
    )
    monkeypatch.setattr(
        routes_competitors,
        "list_competitors_with_pagination",
        lambda db, user, monitored_product_id, page, per_page, include_inactive, include_paused, context: CompetitorsListResponse(
            items=[competitor],
            competitors_total=1,
            competitors_with_price_count=1,
            excluded_due_to_inactive_count=0,
            page=page,
            per_page=per_page,
        ),
    )

    create_response = api_client.post(
        "/competitors/scrape",
        json={
            "monitored_product_id": str(monitored_id),
            "product_url": competitor["url"],
            "name": competitor["name"],
        },
        headers={"Authorization": "Bearer test-access-token"},
    )
    assert create_response.status_code == 202
    assert create_response.json()["message"] == "Concorrente agendado"

    list_response = api_client.get(
        f"/competitors/?monitored_id={monitored_id}",
        headers={"Authorization": "Bearer test-access-token"},
    )
    assert list_response.status_code == 200
    assert list_response.json()["competitors_total"] == 1
    assert list_response.json()["items"][0]["monitored_product_id"] == str(monitored_id)
