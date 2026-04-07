""" Testes de integração controlada para endpoints principais da API. """

from __future__ import annotations

from uuid import uuid4

import pytest

from market_alert.comparisons.routes import routes_comparisons
from market_alert.notifications.routes import routes_notifications
from market_alert.users.routes import routes_settings


pytestmark = pytest.mark.integration


def test_notifications_preferences_and_history_http_contract(
    monkeypatch,
    api_client,
    integration_state,
    integration_current_user,
    integration_now,
) -> None:
    preference_id = uuid4()
    monitored_id = uuid4()
    notification_id = uuid4()
    event_id = uuid4()

    integration_state["notifications"] = [
        {
            "id": notification_id,
            "event_id": event_id,
            "alert_id": None,
            "user_id": integration_current_user.id,
            "monitored_product_id": monitored_id,
            "channel": "email",
            "recipient": integration_current_user.email,
            "subject": "Preco alterado",
            "message": "Coleta simulada gerou notificacao controlada.",
            "dedup_hash": "dedup-1",
            "payload": {"dispatch_mode": "controlled"},
            "priority": 1,
            "cooldown_seconds": 0,
            "status": "pending",
            "attempts": 0,
            "max_attempts": 3,
            "next_attempt_at": None,
            "last_attempt_at": None,
            "sent_at": None,
            "cooldown_expires_at": None,
            "dead_lettered_at": None,
            "created_at": integration_now,
            "updated_at": integration_now,
        }
    ]

    def _upsert_user_notification_preference(
        db,
        user_id,
        alert_type,
        channel,
        monitored_product_id=None,
        destination=None,
        enabled=True,
        cooldown_seconds=0,
        channel_metadata=None,
        commit=True,
    ):
        preference = {
            "id": preference_id,
            "user_id": user_id,
            "monitored_product_id": monitored_product_id,
            "alert_type": alert_type,
            "channel": channel,
            "destination": destination,
            "enabled": enabled,
            "cooldown_seconds": cooldown_seconds,
            "channel_metadata": channel_metadata,
            "last_notified_at": None,
            "created_at": integration_now,
            "updated_at": integration_now,
        }
        integration_state["preferences"] = [preference]
        return preference

    monkeypatch.setattr(
        routes_notifications,
        "upsert_user_notification_preference",
        _upsert_user_notification_preference,
    )
    monkeypatch.setattr(
        routes_notifications,
        "list_user_notification_preferences",
        lambda db, user_id: integration_state["preferences"],
    )
    monkeypatch.setattr(
        routes_notifications,
        "list_notifications_for_user",
        lambda db, user_id, page, per_page: (integration_state["notifications"], len(integration_state["notifications"])),
    )
    monkeypatch.setattr(
        routes_settings,
        "get_profile_settings",
        lambda current_user: {
            "id": current_user.id,
            "name": current_user.name,
            "email": current_user.email,
            "phone_number": current_user.phone_number,
            "email_verified": current_user.email_verified,
            "phone_number_verified": current_user.phone_number_verified,
        },
    )

    create_pref_response = api_client.post(
        "/notifications/preferences",
        json={
            "user_id": str(integration_current_user.id),
            "monitored_product_id": str(monitored_id),
            "alert_type": "price_change",
            "channel": "email",
            "destination": integration_current_user.email,
            "enabled": True,
            "cooldown_seconds": 60,
            "channel_metadata": {"dispatch_mode": "controlled"},
        },
        headers={"Authorization": "Bearer test-access-token"},
    )
    assert create_pref_response.status_code == 201
    assert create_pref_response.json()["channel"] == "email"

    list_pref_response = api_client.get(
        "/notifications/preferences",
        headers={"Authorization": "Bearer test-access-token"},
    )
    assert list_pref_response.status_code == 200
    assert list_pref_response.json()[0]["alert_type"] == "price_change"

    notifications_response = api_client.get(
        "/notifications/",
        headers={"Authorization": "Bearer test-access-token"},
    )
    assert notifications_response.status_code == 200
    assert notifications_response.json()["items"][0]["status"] == "pending"
    assert notifications_response.json()["items"][0]["payload"]["dispatch_mode"] == "controlled"

    profile_response = api_client.get(
        "/settings/profile",
        headers={"Authorization": "Bearer test-access-token"},
    )
    assert profile_response.status_code == 200
    assert profile_response.json()["email"] == integration_current_user.email


def test_comparisons_summary_and_detail_http_contract(
    monkeypatch,
    api_client,
    integration_current_user,
    integration_now,
) -> None:
    monitored_id = uuid4()
    comparison_id = uuid4()
    detail_payload = {
        "id": comparison_id,
        "monitored_product_id": monitored_id,
        "timestamp": integration_now,
        "data": {
            "competitiveness_status": "urgent",
            "competitors_min": 189.9,
            "monitored_price": 199.9,
        },
    }
    summary_payload = {
        "monitored_product_id": monitored_id,
        "comparison_id": comparison_id,
        "last_comparison_at": integration_now,
        "computed_at": integration_now,
        "monitored_price": 199.9,
        "competitors_count": 3,
        "competitors_with_price_count": 2,
        "competitors_mean": 194.9,
        "competitors_min": 189.9,
        "competitors_max": 205.0,
        "position_rank": 3,
        "potential_adjustment": 10.0,
        "ignored_due_to_inactive": False,
        "comparison_insights": "Menor preco do concorrente abaixo do monitorado.",
        "competitiveness_status": "urgent",
        "discrepancies": [],
    }

    monkeypatch.setattr(
        routes_comparisons,
        "get_comparison_summary_for_user",
        lambda db, monitored_id, user: summary_payload,
    )
    monkeypatch.setattr(
        routes_comparisons,
        "get_comparison_detail_for_user",
        lambda db, comparison_id, user: detail_payload,
    )

    summary_response = api_client.get(
        f"/comparisons/{monitored_id}/summary",
        headers={"Authorization": "Bearer test-access-token"},
    )
    assert summary_response.status_code == 200
    assert summary_response.json()["competitiveness_status"] == "urgent"
    assert summary_response.json()["comparison_id"] == str(comparison_id)

    detail_response = api_client.get(
        f"/comparisons/detail/{comparison_id}",
        headers={"Authorization": "Bearer test-access-token"},
    )
    assert detail_response.status_code == 200
    assert detail_response.json()["data"]["competitiveness_status"] == "urgent"
    assert detail_response.json()["monitored_product_id"] == str(monitored_id)
