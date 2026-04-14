""" Testes de integração controlada para fluxo de monitoramento. """

from __future__ import annotations

from contextlib import nullcontext
from copy import deepcopy
from datetime import timedelta
from types import SimpleNamespace
from uuid import uuid4

import pytest

import market_alert.collectors.tasks.collector_product_task as collector_task_module
import market_alert.comparisons.tasks.compare_prices_task as compare_task_module
from market_alert.products.routes import routes_monitored


pytestmark = pytest.mark.integration


def _push_task_request(task, **kwargs):
    task.push_request(**kwargs)
    return task


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
    monitored["competitiveness_status"] = "competitivo"

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
        return SimpleNamespace(
            items=list(integration_state["monitored"].values()),
            meta=SimpleNamespace(
                total=len(integration_state["monitored"]),
                page=page,
                per_page=per_page or len(integration_state["monitored"]) or 1,
            ),
        )

    def _get_monitored_product(db, product_id, user_id):
        return integration_state["monitored"][str(product_id)]

    def _update_monitored_pause_state(db, product_id, user, payload):
        persisted = integration_state["monitored"][str(product_id)]
        persisted["paused"] = payload.paused
        persisted["display_status"] = "paused" if payload.paused else "competitive"
        return SimpleNamespace(**persisted)

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


def test_minimal_controlled_flow_create_collect_compare_and_enqueue_notification(
    monkeypatch,
    api_client,
    integration_state,
    monitored_product_payload,
    integration_now,
    integration_current_user,
) -> None:
    monitored = deepcopy(monitored_product_payload)
    monitored["owner_id"] = integration_current_user.id
    monitored["user_id"] = integration_current_user.id
    monitored["id"] = uuid4()
    monitored["url"] = "https://store.example.com/products/phase2-controlled-flow"
    monitored["normalized_url"] = monitored["url"]
    monitored["created_at"] = integration_now
    monitored["monitored_since"] = integration_now
    monitored["next_check_at"] = integration_now + timedelta(minutes=15)
    monitored["last_scraped_at"] = None
    monitored["last_collected_at"] = None

    collected_payloads: list[dict[str, object]] = []
    enqueued_notifications: list[dict[str, object]] = []

    def _create_monitored_product(db, user, product_data, request):
        integration_state["monitored"][str(monitored["id"])] = dict(monitored)
        return SimpleNamespace(
            id=monitored["id"],
            url=monitored["url"],
            created_at=monitored["created_at"],
            next_check_at=monitored["next_check_at"],
            message="Monitoramento agendado",
            competitor_warning=None,
        )

    monkeypatch.setattr(routes_monitored, "create_monitored_product", _create_monitored_product)

    create_response = api_client.post(
        "/monitored/scrape",
        json={
            "name_identification": monitored["name"],
            "product_url": monitored["url"],
        },
        headers={"Authorization": "Bearer test-access-token"},
    )
    assert create_response.status_code == 202

    monkeypatch.setattr(
        collector_task_module,
        "SessionLocal",
        lambda: nullcontext(SimpleNamespace(name="collector-db")),
    )

    def _collect_product(payload, **kwargs):
        collected_payloads.append(dict(payload))
        persisted = integration_state["monitored"][payload["monitored_id"]]
        persisted["current_price"] = "199.90"
        persisted["last_status"] = "collected"
        persisted["last_scraped_at"] = integration_now
        persisted["last_collected_at"] = integration_now
        return "collected", SimpleNamespace(status="success", error_code=None), None

    monkeypatch.setattr(collector_task_module, "collect_product", _collect_product)
    monkeypatch.setattr(collector_task_module, "_should_block_invalid_url", lambda result: False)
    monkeypatch.setattr(
        collector_task_module,
        "_should_schedule_temporary_retry",
        lambda result, reason: False,
    )

    _push_task_request(
        collector_task_module.collect_product_task,
        id="collect-controlled-1",
        retries=0,
        delivery_info={"routing_key": "scraping"},
    )
    try:
        collect_result = collector_task_module.collect_product_task.run(
            payload={
                "version": 1,
                "kind": "monitored",
                "monitored_id": str(monitored["id"]),
                "url": monitored["url"],
                "trace_id": str(uuid4()),
                "user_id": str(integration_current_user.id),
                "name": monitored["name"],
            }
        )
    finally:
        collector_task_module.collect_product_task.pop_request()

    assert collect_result["outcome"] == "collected"
    assert collected_payloads[0]["monitored_id"] == str(monitored["id"])

    monkeypatch.setattr(
        compare_task_module,
        "SessionLocal",
        lambda: nullcontext(SimpleNamespace(name="compare-db")),
    )
    monkeypatch.setattr(
        compare_task_module,
        "run_price_comparison",
        lambda db, monitored_uuid: {
            "summary": {"competitors_with_price_count": 1},
            "lowest_competitor": 189.90,
            "highest_competitor": 205.00,
        },
    )
    monkeypatch.setattr(
        compare_task_module,
        "get_monitored_product_by_id",
        lambda db, monitored_uuid: SimpleNamespace(
            id=monitored_uuid,
            user_id=integration_current_user.id,
            availability=True,
        ),
    )
    monkeypatch.setattr(compare_task_module, "get_user_by_id", lambda db, user_id: integration_current_user)
    monkeypatch.setattr(compare_task_module, "fetch_recent_prices", lambda db, monitored_id: (189.90, 199.90))
    monkeypatch.setattr(
        compare_task_module,
        "evaluate_and_create_notifications",
        lambda *args, **kwargs: [str(uuid4())],
    )
    monkeypatch.setattr(
        compare_task_module,
        "enqueue_pending_notifications",
        lambda db, notification_ids, trace_id=None: enqueued_notifications.append(
            {"notification_ids": list(notification_ids), "trace_id": trace_id}
        ),
    )

    _push_task_request(
        compare_task_module.compare_prices_task,
        id="compare-controlled-1",
        delivery_info={"routing_key": "compare"},
    )
    try:
        compare_task_module.compare_prices_task.run(
            monitored_id=str(monitored["id"]),
            price_changed=True,
            availability_changed=False,
            trace_id="trace-controlled-flow",
        )
    finally:
        compare_task_module.compare_prices_task.pop_request()

    assert len(enqueued_notifications) == 1
    assert len(enqueued_notifications[0]["notification_ids"]) == 1
    assert enqueued_notifications[0]["trace_id"] == "trace-controlled-flow"
