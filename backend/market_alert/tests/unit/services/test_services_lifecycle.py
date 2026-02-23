"""Testes unitários dos services de ciclo de vida com mocks de dependências."""

from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from market_alert.models.models_products import MonitoredProduct
from unittest.mock import Mock
import uuid

from fastapi import HTTPException

from backend.shared.schemas.shared_schemas_products import (
    CompetitorProductCreateScraping,
    MonitoredProductCreateScraping,
)
from market_alert.services import services_competitor_lifecycle as competitor_service
from market_alert.services import services_monitored_lifecycle as monitored_service


def test_create_monitored_product_orquestra_camadas_com_mocks(monkeypatch, db_session, user) -> None:
    """Valida sequência service->domain->crud->orquestrador sem IO externo."""
    pending = MonitoredProduct(
        id=uuid.uuid4(),
        user_id=user.id,
        name_identification="Produto",
        monitoring_type="scraping",
        product_url="https://loja.com/p/1",
        normalized_url="https://loja.com/p/1",
        created_at=datetime.now(timezone.utc),
    )

    monkeypatch.setattr(monitored_service, "normalize_and_validate_product_url", lambda url: (url, None))
    monkeypatch.setattr(monitored_service, "get_monitored_product_by_user_and_url", lambda *args, **kwargs: None)
    monkeypatch.setattr(monitored_service, "parse_rate_limit_config", lambda *_: None)
    monkeypatch.setattr(monitored_service, "create_pending_monitored_product", lambda **kwargs: pending)
    monkeypatch.setattr(db_session, "commit", lambda: None)
    monkeypatch.setattr(db_session, "refresh", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(
        monitored_service,
        "compute_next_check_at",
        lambda *args, **kwargs: SimpleNamespace(next_check_at=datetime.now(timezone.utc), stability_score=0),
    )
    enqueue_collect = Mock()
    monkeypatch.setattr(monitored_service, "enqueue_collect", enqueue_collect)
    monkeypatch.setattr(monitored_service, "enqueue_monitored_now", lambda *_args, **_kwargs: True)

    payload = MonitoredProductCreateScraping(name_identification="Produto", product_url="https://loja.com/p/1")
    response = monitored_service.create_monitored_product(db=db_session, user=user, product_data=payload)

    assert response.id == pending.id
    assert enqueue_collect.called


def test_create_competitor_scrape_request_valida_monitored_pausado(monkeypatch, db_session, user) -> None:
    """Garante bloqueio quando monitorado está pausado antes de persistir concorrente."""
    monitored_stub = SimpleNamespace(id=uuid.uuid4(), normalized_url="https://loja.com/p/1", paused=True)
    monkeypatch.setattr(competitor_service, "normalize_and_validate_product_url", lambda url: (url, None))
    monkeypatch.setattr(competitor_service, "ensure_user_can_access_monitored", lambda **kwargs: monitored_stub)

    payload = CompetitorProductCreateScraping(
        monitored_product_id=monitored_stub.id,
        product_url="https://concorrente.com/p/2",
        name="Concorrente",
    )

    try:
        competitor_service.create_competitor_scrape_request(db=db_session, user=user, product_data=payload)
    except HTTPException as exc:
        assert exc.status_code == 403
    else:
        raise AssertionError("Era esperado HTTPException para monitorado pausado")
