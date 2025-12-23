""" Testes para persistência de payloads na comparação de preços """

from datetime import datetime, timezone
from uuid import UUID, uuid4
from decimal import Decimal

from market_alert.services import services_comparison as comparison_service
from market_alert.enums.enums_products import MonitoredStatus


def _install_common_fixtures(monkeypatch, raw_result, *, store_raw: bool, captured: dict) -> UUID:
    """ Prepara dependências da comparação para focar na persistência do payload """

    monitored_id = uuid4()

    class _Monitored:
        def __init__(self, identifier: UUID) -> None:
            self.id = identifier
            self.user_id = uuid4()
            self.status = MonitoredStatus.active
            self.availability = True
            monitored_price = raw_result.get("monitored_price")
            self.current_price = (
                Decimal(str(monitored_price)) if monitored_price is not None else None
            )
            self.last_status = "available"

    class _Comparison:
        def __init__(self) -> None:
            self.id = uuid4()
            self.timestamp = datetime.now(timezone.utc)

    def fake_get_monitored_product_by_id(db, monitored_uuid):
        return _Monitored(monitored_uuid)

    def fake_get_competitors_by_monitored_id(db, monitored_uuid):
        return []

    def fake_compare_prices(monitored, competitors, tolerance):
        return raw_result

    def fake_create_price_comparison(db, monitored_uuid, data):
        captured["payload"] = data
        return _Comparison()

    def fake_build_summary_from_result(*args, **kwargs):
        return {"computed": True}

    def fake_upsert_price_comparison_summary(*args, **kwargs):
        return None

    monkeypatch.setattr(
        comparison_service, "get_monitored_product_by_id", fake_get_monitored_product_by_id
    )
    monkeypatch.setattr(
        comparison_service, "get_competitors_by_monitored_id", fake_get_competitors_by_monitored_id
    )
    monkeypatch.setattr(comparison_service, "compare_prices", fake_compare_prices)
    monkeypatch.setattr(
        comparison_service, "create_price_comparison", fake_create_price_comparison
    )
    monkeypatch.setattr(
        comparison_service,
        "_build_summary_from_result",
        fake_build_summary_from_result,
    )
    monkeypatch.setattr(
        comparison_service,
        "upsert_price_comparison_summary",
        fake_upsert_price_comparison_summary,
    )
    monkeypatch.setattr(
        comparison_service.settings, "COMPARISON_STORE_RAW_RESULT", store_raw
    )

    return monitored_id


def test_run_price_comparison_persists_full_payload_when_enabled(monkeypatch):
    """ Garante armazenamento do payload completo quando a flag está ligada """

    captured: dict = {}
    raw_result = {
        "monitored_price": "10.00",
        "alerts": [{"type": "alerta"}],
        "discrepancies": [{"price": "9.00"}],
        "lowest_competitor": {"price": "9.00", "fonte": "x"},
        "highest_competitor": {"price": "12.00"},
        "extra": "deve ser mantido",
    }
    monitored_id = _install_common_fixtures(
        monkeypatch, raw_result, store_raw=True, captured=captured
    )

    comparison_service.run_price_comparison(db=None, monitored_id=monitored_id)

    stored_payload = captured["payload"]
    for key, value in raw_result.items():
        assert stored_payload[key] == value
    assert "summary" in stored_payload
    assert "comparison_id" in stored_payload


def test_run_price_comparison_stores_compact_payload_by_default(monkeypatch):
    """ Usa snapshot enxuto quando a flag de armazenamento bruto está desativada """

    captured: dict = {}
    raw_result = {
        "monitored_price": "15.00",
        "alerts": [],
        "discrepancies": [{"price": "14.00"}],
        "lowest_competitor": {"price": "14.00"},
        "highest_competitor": {"price": "16.00"},
        "ignorar": True,
    }
    monitored_id = _install_common_fixtures(
        monkeypatch, raw_result, store_raw=False, captured=captured
    )

    comparison_service.run_price_comparison(db=None, monitored_id=monitored_id)

    assert captured["payload"] == {
        "monitored_price": "15.00",
        "alerts": [],
        "discrepancies": [{"price": "14.00"}],
        "lowest_competitor": {"price": "14.00"},
        "highest_competitor": {"price": "16.00"},
    }

def test_run_price_comparison_skips_inactive_monitored(monkeypatch) -> None:
    """ Suprime competitividade quando o monitorado está indisponível. """

    monitored_id = uuid4()
    captured: dict = {}

    class _Monitored:
        def __init__(self, identifier: UUID) -> None:
            self.id = identifier
            self.user_id = uuid4()
            self.status = MonitoredStatus.inactive
            self.availability = False
            self.current_price = None
            self.last_status = "unavailable"

    class _Comparison:
        def __init__(self) -> None:
            self.id = uuid4()
            self.timestamp = datetime.now(timezone.utc)

    def fake_get_monitored_product_by_id(db, monitored_uuid):
        return _Monitored(monitored_uuid)

    def fake_get_competitors_by_monitored_id(db, monitored_uuid):
        return []

    def fake_create_price_comparison(db, monitored_uuid, data):
        captured["payload"] = data
        return _Comparison()

    def fake_upsert_price_comparison_summary(db, monitored_id, comparison_id, summary):
        captured["summary"] = summary
        return None

    monkeypatch.setattr(
        comparison_service, "get_monitored_product_by_id", fake_get_monitored_product_by_id
    )
    monkeypatch.setattr(
        comparison_service, "get_competitors_by_monitored_id", fake_get_competitors_by_monitored_id
    )
    monkeypatch.setattr(
        comparison_service, "create_price_comparison", fake_create_price_comparison
    )
    monkeypatch.setattr(
        comparison_service, "upsert_price_comparison_summary", fake_upsert_price_comparison_summary
    )

    result, alerts = comparison_service.run_price_comparison(db=None, monitored_id=monitored_id)

    assert alerts == []
    assert captured["payload"]["ignored_due_to_inactive"] is True
    assert captured["payload"]["reason"] == "monitored_unavailable"
    summary = result["summary"]
    assert summary["ignored_due_to_inactive"] is True
    assert summary["competitors_with_price_count"] == 0
    assert summary["monitored_price"] is None
    