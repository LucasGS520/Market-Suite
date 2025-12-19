"""Valida que coletor ignora monitorados pausados."""

from datetime import datetime, timezone
from uuid import uuid4

import pytest

from market_alert.enums.enums_products import MonitoringType, MonitoredStatus
from market_alert.models.models_price_history import PriceHistory
from market_alert.models.models_products import MonitoredProduct
from market_alert.tasks.collector_product_task import collect_product
from shared.utils.redis_client import get_redis_client


@pytest.fixture(autouse=True)
def _patch_locks(monkeypatch: pytest.MonkeyPatch) -> None:
    """Stub de locks e Redis para impedir dependências externas."""

    monkeypatch.setattr(
        "market_alert.tasks.collector_product_task.acquire_product_lock", lambda *_, **__: (True, "owner")
    )
    monkeypatch.setattr("market_alert.tasks.collector_product_task.release_product_lock", lambda *_, **__: None)
    redis_client = get_redis_client()
    monkeypatch.setattr("market_alert.tasks.collector_product_task.is_scraping_suspended", lambda: False)
    monkeypatch.setattr("market_alert.tasks.collector_product_task.redis_client", redis_client, raising=False)


def test_collector_skips_paused_monitored(db_session, test_user, prepare_test_database):
    """Quando o monitorado está pausado a coleta devolve no_result e não persiste histórico."""

    monitored = MonitoredProduct(
        id=uuid4(),
        user_id=test_user.id,
        name_identification="Smartphone Pausado",
        monitoring_type=MonitoringType.scraping,
        product_url="https://example.com/smartphone",
        normalized_url="https://example.com/smartphone",
        status=MonitoredStatus.active,
        paused=True,
        paused_at=datetime.now(timezone.utc),
    )
    db_session.add(monitored)
    db_session.commit()

    outcome, result = collect_product(
        {"monitored_id": str(monitored.id), "url": monitored.product_url},
        use_lock=False,
        dispatch_comparison=False,
        logger_bound=None,
    )

    assert outcome == "no_result"
    assert result is not None
    assert result.status == "no_result"

    assert db_session.query(PriceHistory).count() == 0
    