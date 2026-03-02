"""Testes de integração dos fluxos de ciclo de vida sem dependências externas."""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
import uuid

from fastapi import FastAPI
from fastapi.testclient import TestClient

from shared.infra.db import get_db
from shared.schemas.shared_schemas_scraper import ScrapeResult

from market_alert.models.models_products import MonitoredProduct
from market_alert.products.routes.routes_monitored import router as monitored_router
from market_alert.products.routes.routes_monitored import get_current_user
from market_alert.collectors.tasks import collector_product_task


def test_fluxo_ponta_a_ponta_criacao_monitored_via_rota(monkeypatch, db_session, user) -> None:
    """Exercita Route -> Service -> CRUD -> DB -> Domain para criação."""
    app = FastAPI()
    app.include_router(monitored_router)

    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_user] = lambda: user

    from backend.market_alert.products.services import services_monitored_lifecycle as lifecycle

    monkeypatch.setattr(lifecycle, "normalize_and_validate_product_url", lambda url: (url, None))
    monkeypatch.setattr(lifecycle, "parse_rate_limit_config", lambda *_: None)
    monkeypatch.setattr(lifecycle, "enqueue_collect", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(lifecycle, "enqueue_monitored_now", lambda *_args, **_kwargs: True)

    client = TestClient(app)
    response = client.post(
        "/monitored/scrape",
        json={"name_identification": "Produto Integração", "product_url": "https://loja.com/p/novo"},
    )

    assert response.status_code == 202
    saved = (
        db_session.query(MonitoredProduct)
        .filter(MonitoredProduct.normalized_url == "https://loja.com/p/novo")
        .first()
    )
    assert saved is not None
    assert saved.next_check_at is not None


def test_fluxo_coleta_task_atualiza_monitorado(monkeypatch, db_session, monitored) -> None:
    """Mocka scrape da task e valida atualização + recálculo de agendamento."""
    payload = {
        "kind": "monitored",
        "monitored_id": str(monitored.id),
        "url": monitored.product_url,
        "user_id": str(monitored.user_id),
        "trace_id": str(uuid.uuid4()),
    }

    def fake_scrape_monitored_product(**kwargs):
        monitored_row = kwargs["db"].query(MonitoredProduct).filter(MonitoredProduct.id == monitored.id).first()
        monitored_row.current_price = Decimal("110.00")
        monitored_row.last_checked = datetime.now(timezone.utc)
        monitored_row.next_check_at = datetime.now(timezone.utc)
        kwargs["db"].commit()
        return ScrapeResult(status="success", product_id=str(monitored.id), http_status=200)

    monkeypatch.setattr(collector_product_task, "is_scraping_suspended", lambda: False)
    monkeypatch.setattr(collector_product_task, "scrape_monitored_product", fake_scrape_monitored_product)

    status, result, reason = collector_product_task.collect_product(
        payload,
        use_lock=False,
        dispatch_comparison=False,
        db=db_session,
    )

    db_session.refresh(monitored)
    assert status in {"processed", "success"}
    assert reason is None
    assert result is not None
    assert monitored.current_price == Decimal("110.00")
    