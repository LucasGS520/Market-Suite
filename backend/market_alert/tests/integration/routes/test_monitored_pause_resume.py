""" Testes de pausa, retomada e remoção de monitorados via API. """

from datetime import datetime, timezone
from uuid import uuid4

import pytest

from market_alert.enums.enums_products import MonitoringType, MonitoredStatus, ProductStatus
from market_alert.models.models_price_history import PriceHistory
from market_alert.models.models_products import CompetitorProduct, MonitoredProduct
from shared.utils.url_validation import normalize_product_url_for_storage


@pytest.fixture(autouse=True)
def _stub_enqueue(monkeypatch: pytest.MonkeyPatch) -> None:
    """Evita enfileiramento real de scraping durante os testes."""

    monkeypatch.setattr(
        "market_alert.services.services_monitored.enqueue_monitored_collection", lambda *_, **__: None
    )
    monkeypatch.setattr(
        "market_alert.orchestrator.collector_service_orchestrator.enqueue_collect", lambda *_, **__: None
    )


def _create_monitored(db_session, user_id):
    """Cria produto monitorado básico para os fluxos de teste."""

    monitored = MonitoredProduct(
        id=uuid4(),
        user_id=user_id,
        name_identification="Notebook Gamer",
        monitoring_type=MonitoringType.scraping,
        product_url="https://example.com/produto-1",
        normalized_url=normalize_product_url_for_storage("https://example.com/produto-1"),
        status=MonitoredStatus.active,
        current_price=199.9,
        next_check_at=datetime.now(timezone.utc),
    )
    db_session.add(monitored)
    db_session.commit()
    return monitored


def test_pause_and_resume_monitored(client, db_session, test_user, prepare_test_database):
    """Garante que pausa e retomada atualizam flags e janela de rechecagem."""

    monitored = _create_monitored(db_session, test_user.id)

    pause_response = client.put(f"/monitored/{monitored.id}/paused", json={"paused": True})
    assert pause_response.status_code == 200
    paused_payload = pause_response.json()
    assert paused_payload["paused"] is True
    assert paused_payload["paused_at"] is not None

    db_session.refresh(monitored)
    assert monitored.paused is True
    assert monitored.paused_at is not None

    resume_response = client.put(f"/monitored/{monitored.id}/paused", json={"paused": False})
    assert resume_response.status_code == 200
    resumed_payload = resume_response.json()
    assert resumed_payload["paused"] is False
    assert resumed_payload["next_check_at"] is not None

    db_session.refresh(monitored)
    assert monitored.paused is False
    assert monitored.paused_at is None
    assert monitored.next_check_at is not None


def test_delete_monitored_removes_dependencies(client, db_session, test_user, prepare_test_database):
    """Remove monitorado, históricos e concorrentes de forma atômica."""

    monitored = _create_monitored(db_session, test_user.id)

    competitor = CompetitorProduct(
        id=uuid4(),
        monitored_product_id=monitored.id,
        name_competitor="Loja X",
        product_url="https://example.com/concorrente-x",
        current_price=189.9,
        status=ProductStatus.available,
    )
    db_session.add(competitor)
    db_session.flush()

    history_entry = PriceHistory(
        id=uuid4(),
        monitored_product_id=monitored.id,
        competitor_product_id=competitor.id,
        price_before=199.9,
        price_after=189.9,
        captured_at=datetime.now(timezone.utc),
    )
    db_session.add(history_entry)
    db_session.commit()

    response = client.delete(f"/monitored/{monitored.id}")
    assert response.status_code == 204

    assert db_session.query(MonitoredProduct).count() == 0
    assert db_session.query(CompetitorProduct).count() == 0
    assert db_session.query(PriceHistory).count() == 0
    