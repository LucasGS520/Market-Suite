from datetime import datetime, timezone
from uuid import UUID

import pytest

from backend.market_alert.tasks import monitor_recheck_tasks


class DummySession:
    """Contexto de sessão fictício para isolar efeitos colaterais."""
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

class DummyMetric:
    """ Permite contar chamadas de métricas em testes sem prometheus real """

    def __init__(self):
        self.calls: list[dict] = []

    def labels(self, **kwargs):
        self.calls.append(kwargs)
        return self 
    
    def inc(self, value: int = 1):
        self.calls.append({"inc": value})

    def observe(self, value):
        self.calls.append({"observe": value})

class DummyMonitored:
    """Estrutura mínima para simular monitorados em orquestração."""

    def __init__(self, product_id: UUID, user_id: UUID):
        self.id = product_id
        self.user_id = user_id
        self.product_url = "http://produto"
        self.name_identification = "Produto"
        self.status = None
        self.last_checked = datetime(2024, 1, 1, tzinfo=timezone.utc)
        self.check_interval = 10

class DummyCompetitor:
    """ Estrutura mínima para simular concorrentes associados """

    def __init__(self, competitor_id: UUID, monitored_id: UUID):
        self.id = competitor_id
        self.monitored_product_id = monitored_id
        self.product_url = "http://concorrente"

def _install_metric_mocks(monkeypatch):
    monitored_metric = DummyMetric()
    competitor_metric = DummyMetric()
    histogram_metric = DummyMetric() 

    monkeypatch.setattr(monitor_recheck_tasks, "RECHECK_MONITORED_RESULT_TOTAL", monitored_metric)
    monkeypatch.setattr(monitor_recheck_tasks, "RECHECK_COMPETITOR_RESULT_TOTAL", competitor_metric)
    monkeypatch.setattr(monitor_recheck_tasks, "SCRAPING_LATENCY_SECONDS", histogram_metric)

    return monitored_metric, competitor_metric, histogram_metric

def test_recheck_monitored_product_aborts_on_monitor_error(monkeypatch):
    """Falhas no monitorado encerram o fluxo e liberam a flag corretamente."""
    monitored_id = UUID("123e4567-e89b-12d3-a456-426655440000")
    monitored = DummyMonitored(monitored_id, monitored_id)
    finalize_calls = {}

    _install_metric_mocks(monkeypatch)

    monkeypatch.setattr(monitor_recheck_tasks, "SessionLocal", lambda: DummySession())
    monkeypatch.setattr(monitor_recheck_tasks, "is_scraping_suspended", lambda: False)
    monkeypatch.setattr(monitor_recheck_tasks, "get_monitored_product_by_id", lambda db, mid: monitored)
    monkeypatch.setattr(monitor_recheck_tasks, "get_competitors_by_monitored_id", lambda db, mid: [])
    monkeypatch.setattr(monitor_recheck_tasks, "_mark_recheck_started", lambda *a, **k: True)
    monkeypatch.setattr(
        monitor_recheck_tasks,
        "_collect_monitored_single",
        lambda *a, **k: monitor_recheck_tasks.CollectionOutcome(status="error", reason="boom", product_id=monitored_id),
    )
    monkeypatch.setattr(monitor_recheck_tasks, "run_price_comparison", lambda *a, **k: finalize_calls.setdefault("comparison", True))

    def fake_finalize(db, product_id, *, last_checked, next_check_at):
        finalize_calls["last_checked"] = last_checked
        finalize_calls["next_check_at"] = next_check_at

    monkeypatch.setattr(monitor_recheck_tasks, "_finalize_recheck_state", fake_finalize)

    result = monitor_recheck_tasks.recheck_monitored_product.run(str(monitored_id))

    assert result == "error"
    assert finalize_calls["last_checked"] == monitored.last_checked
    assert "comparison" not in finalize_calls

def test_recheck_monitored_product_runs_comparison_on_changes(monkeypatch):
    """Alterações em monitorado ou concorrente acionam comparação inline."""

    monitored_id = UUID("123e4567-e89b-12d3-a456-426655440010")
    competitor_id = UUID("123e4567-e89b-12d3-a456-426655440011")
    monitored = DummyMonitored(monitored_id, monitored_id)
    competitor = DummyCompetitor(competitor_id, monitored_id)

    _, _, _ = _install_metric_mocks(monkeypatch)

    monkeypatch.setattr(monitor_recheck_tasks, "SessionLocal", lambda: DummySession())
    monkeypatch.setattr(monitor_recheck_tasks, "is_scraping_suspended", lambda: False)
    monkeypatch.setattr(monitor_recheck_tasks, "get_monitored_product_by_id", lambda db, mid: monitored)
    monkeypatch.setattr(monitor_recheck_tasks, "get_competitors_by_monitored_id", lambda db, mid: [competitor])
    monkeypatch.setattr(monitor_recheck_tasks, "_mark_recheck_started", lambda *a, **k: True)

    monkeypatch.setattr(
        monitor_recheck_tasks,
        "_collect_monitored_single",
        lambda *a, **k: monitor_recheck_tasks.CollectionOutcome(status="success_new", product_id=monitored_id),
    )
    monkeypatch.setattr(
        monitor_recheck_tasks,
        "_collect_competitor_single",
        lambda *a, **k: monitor_recheck_tasks.CollectionOutcome(status="success_no_change", product_id=competitor_id),
    )

    comparison_calls = {}
    monkeypatch.setattr(monitor_recheck_tasks, "run_price_comparison", lambda *a, **k: comparison_calls.setdefault("called", True))
    monkeypatch.setattr(monitor_recheck_tasks, "_finalize_recheck_state", lambda *a, **k: None)

    result = monitor_recheck_tasks.recheck_monitored_product.run(str(monitored_id))

    assert result == "completed"
    assert comparison_calls["called"] is True

def test_enqueue_due_monitored_respects_suspension(monkeypatch):
    """Agendador deve ignorar execução quando suspensão global está ativa."""

    _, _, histogram = _install_metric_mocks(monkeypatch)
    monkeypatch.setattr(monitor_recheck_tasks, "SessionLocal", lambda: DummySession())
    monkeypatch.setattr(monitor_recheck_tasks, "is_scraping_suspended", lambda: True)
    monkeypatch.setattr(monitor_recheck_tasks, "schedule_due_monitored", lambda db: 5)

    dispatched = monitor_recheck_tasks.enqueue_due_monitored.run()

    assert dispatched == 0
    assert histogram.calls, "histograma deve registrar a execução mesmo em suspensão"
        