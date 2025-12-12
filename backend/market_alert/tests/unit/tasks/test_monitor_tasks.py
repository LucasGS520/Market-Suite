from datetime import datetime, timedelta, timezone
from uuid import UUID

import pytest

from backend.market_alert.tasks import monitor_recheck_tasks


class DummySession:
    """Permite contar chamadas de métricas em testes sem prometheus real."""
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

class DummyMetric:
    """ Permite contar chamadas de métricas em testes sem prometheus real """

    def __init__(self):
        self.calls: list[dict] = []

    def labels(self, **kwargs):
        self.calls.append({"labels": kwargs})
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
        self.checking_in_progress = False

class DummyCompetitor:
    """ Estrutura mínima para simular concorrentes associados """

    def __init__(self, competitor_id: UUID, monitored_id: UUID):
        self.id = competitor_id
        self.monitored_product_id = monitored_id
        self.product_url = "http://concorrente"

def _install_metric_mocks(monkeypatch: pytest.MonkeyPatch):
    monitored_metric = DummyMetric()
    competitor_metric = DummyMetric()
    histogram_metric = DummyMetric()
    finalize_metric = DummyMetric()
    mark_metric = DummyMetric()


    monkeypatch.setattr(monitor_recheck_tasks, "RECHECK_MONITORED_RESULT_TOTAL", monitored_metric)
    monkeypatch.setattr(monitor_recheck_tasks, "RECHECK_COMPETITOR_RESULT_TOTAL", competitor_metric)
    monkeypatch.setattr(monitor_recheck_tasks, "SCRAPING_LATENCY_SECONDS", histogram_metric)
    monkeypatch.setattr(monitor_recheck_tasks, "RECHECK_FINALIZE_FAILED_TOTAL", finalize_metric)
    monkeypatch.setattr(monitor_recheck_tasks, "RECHECK_MARK_FAILED_TOTAL", mark_metric)

    return monitored_metric, competitor_metric, histogram_metric, finalize_metric, mark_metric

def _changed_result():
    return type("Result", (), {"price_changed": True, "availability_changed": False})()

def test_recheck_monitored_product_aborts_on_monitor_error(monkeypatch: pytest.MonkeyPatch):
    """Falhas no monitorado encerram o fluxo e liberam a flag corretamente."""
    monitored_id = UUID("123e4567-e89b-12d3-a456-426655440000")
    monitored = DummyMonitored(monitored_id, monitored_id)
    finalize_calls: dict[str, datetime] = {}

    _install_metric_mocks(monkeypatch)

    monkeypatch.setattr(monitor_recheck_tasks, "SessionLocal", lambda: DummySession())
    monkeypatch.setattr(monitor_recheck_tasks, "is_scraping_suspended", lambda: False)
    monkeypatch.setattr(monitor_recheck_tasks, "get_monitored_product_by_id", lambda db, mid: monitored)
    monkeypatch.setattr(monitor_recheck_tasks, "get_competitors_by_monitored_id", lambda db, mid: [])
    monkeypatch.setattr(
        monitor_recheck_tasks,
        "_compute_next_check_at",
        lambda m, ref: ref + timedelta(seconds=10),
    )

    def fake_mark(*_a, **_k):
        monitored.checking_in_progress = True
        return "started"

    monkeypatch.setattr(monitor_recheck_tasks, "_mark_recheck_started", fake_mark)
    monkeypatch.setattr(
        monitor_recheck_tasks,
        "_collect_inline",
        lambda *a, **k: monitor_recheck_tasks.CollectionOutcome(
            status="error", reason="boom", product_id=monitored_id
        ),
    )
    monkeypatch.setattr(
        monitor_recheck_tasks,
        "run_price_comparison",
        lambda *a, **k: finalize_calls.setdefault("comparison", True),
    )

    def fake_finalize(db, product_id, *, last_checked, next_check_at):
        finalize_calls["last_checked"] = last_checked
        finalize_calls["next_check_at"] = next_check_at
        monitored.checking_in_progress = False

    monkeypatch.setattr(monitor_recheck_tasks, "_finalize_recheck_state", fake_finalize)

    result = monitor_recheck_tasks.recheck_monitored_product.run(str(monitored_id))

    assert result == "error"
    assert finalize_calls["last_checked"] == monitored.last_checked
    assert monitored.checking_in_progress is False
    assert "comparison" not in finalize_calls

def test_recheck_mark_failure_is_reported(monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture):
    """Falha ao marcar rechecagem deve registrar e impedir coleta subsequente."""

    monitored_id = UUID("123e4567-e89b-12d3-a456-426655440099")
    monitored = DummyMonitored(monitored_id, monitored_id)

    _, _, _, _, mark_metric = _install_metric_mocks(monkeypatch)
    monkeypatch.setattr(monitor_recheck_tasks, "is_scraping_suspended", lambda: False)
    monkeypatch.setattr(monitor_recheck_tasks, "get_monitored_product_by_id", lambda db, mid: monitored)
    monkeypatch.setattr(monitor_recheck_tasks, "get_competitors_by_monitored_id", lambda db, mid: [])
    monkeypatch.setattr(monitor_recheck_tasks, "_compute_next_check_at", lambda m, ref: ref + timedelta(seconds=10))

    class FailingSession:
        """Simula erro de atualização transacional ao marcar rechecagem."""

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def begin(self):
            class _Ctx:
                def __enter__(self_inner):
                    raise RuntimeError("db_failure")

                def __exit__(self_inner, exc_type, exc, tb):
                    return False

            return _Ctx()

    monkeypatch.setattr(monitor_recheck_tasks, "SessionLocal", lambda: FailingSession())

    def fail_collect(*_a, **_k):
        raise AssertionError("coleta não deve ser chamada")

    monkeypatch.setattr(monitor_recheck_tasks, "_collect_inline", fail_collect)

    caplog.set_level("WARNING")

    result = monitor_recheck_tasks.recheck_monitored_product.run(str(monitored_id))

    assert result == "mark_failed"
    assert any("recheck_mark_failed" in rec.message for rec in caplog.records)
    assert mark_metric.calls, "métrica de falha deve ser incrementada"

def test_recheck_sets_and_clears_checking_flag_on_success_and_failure(monkeypatch: pytest.MonkeyPatch):
    """Rechecagem deve limpar a flag tanto em sucesso quanto ao abortar."""

    monitored_id = UUID("123e4567-e89b-12d3-a456-426655440010")
    monitored = DummyMonitored(monitored_id, monitored_id)
    finalize_calls: list[tuple[datetime | None, datetime]] = []
    comparison_calls: dict[str, bool] = {}

    _install_metric_mocks(monkeypatch)
    monkeypatch.setattr(monitor_recheck_tasks, "SessionLocal", lambda: DummySession())
    monkeypatch.setattr(monitor_recheck_tasks, "is_scraping_suspended", lambda: False)
    monkeypatch.setattr(monitor_recheck_tasks, "get_monitored_product_by_id", lambda db, mid: monitored)
    monkeypatch.setattr(monitor_recheck_tasks, "get_competitors_by_monitored_id", lambda db, mid: [])
    monkeypatch.setattr(
        monitor_recheck_tasks,
        "_compute_next_check_at",
        lambda m, ref: ref + timedelta(seconds=5),
    )

    def fake_mark(*_a, **_k):
        monitored.checking_in_progress = True
        return "started"

    monkeypatch.setattr(monitor_recheck_tasks, "_mark_recheck_started", fake_mark)
    monkeypatch.setattr(
        monitor_recheck_tasks,
        "_collect_inline",
        lambda *a, **k: monitor_recheck_tasks.CollectionOutcome(
            status="success", product_id=monitored_id, result=_changed_result()
        ),
    )
    monkeypatch.setattr(
        monitor_recheck_tasks,
        "run_price_comparison",
        lambda *a, **k: comparison_calls.setdefault("called", True),
    )

    def fake_finalize(db, product_id, *, last_checked, next_check_at):
        finalize_calls.append((last_checked, next_check_at))
        monitored.last_checked = last_checked
        monitored.checking_in_progress = False

    monkeypatch.setattr(monitor_recheck_tasks, "_finalize_recheck_state", fake_finalize)

    success_result = monitor_recheck_tasks.recheck_monitored_product.run(str(monitored_id))

    assert success_result == "completed"
    assert finalize_calls, "finalização deve ocorrer após sucesso"
    last_checked, next_check = finalize_calls[-1]
    assert last_checked is not None and last_checked.tzinfo == timezone.utc
    assert next_check == last_checked + timedelta(seconds=5)
    assert monitored.checking_in_progress is False
    assert comparison_calls["called"] is True

    #Força nova execução com falha para garantir limpeza da flag
    monitored.checking_in_progress = False

    monkeypatch.setattr(
        monitor_recheck_tasks,
        "_collect_inline",
        lambda *a, **k: monitor_recheck_tasks.CollectionOutcome(
            status="error", reason="boom", product_id=monitored_id
        ),
    )
    finalize_calls.clear()

    failure_result = monitor_recheck_tasks.recheck_monitored_product.run(str(monitored_id))

    assert failure_result == "error"
    assert finalize_calls[0][0] == monitored.last_checked
    assert monitored.checking_in_progress is False


def test_recheck_monitored_product_runs_comparison_on_changes(monkeypatch: pytest.MonkeyPatch):
    """Alterações detectadas em concorrentes acionam a comparação inline."""

    monitored_id = UUID("123e4567-e89b-12d3-a456-426655440020")
    competitor_id = UUID("123e4567-e89b-12d3-a456-426655440021")
    monitored = DummyMonitored(monitored_id, monitored_id)
    competitor = DummyCompetitor(competitor_id, monitored_id)
    comparison_calls: dict[str, bool] = {}

    _install_metric_mocks(monkeypatch)
    monkeypatch.setattr(monitor_recheck_tasks, "SessionLocal", lambda: DummySession())
    monkeypatch.setattr(monitor_recheck_tasks, "is_scraping_suspended", lambda: False)
    monkeypatch.setattr(monitor_recheck_tasks, "get_monitored_product_by_id", lambda db, mid: monitored)
    monkeypatch.setattr(monitor_recheck_tasks, "get_competitors_by_monitored_id", lambda db, mid: [competitor])
    monkeypatch.setattr(
        monitor_recheck_tasks,
        "_compute_next_check_at",
        lambda m, ref: ref + timedelta(seconds=5),
    )
    monkeypatch.setattr(monitor_recheck_tasks, "_mark_recheck_started", lambda *a, **k: True)

    def fake_collect(payload, *, product_id, kind, logger_bound):
        if kind == "monitored":
            return monitor_recheck_tasks.CollectionOutcome(status="not_modified", product_id=product_id)
        return monitor_recheck_tasks.CollectionOutcome(
            status="success", product_id=product_id, result=_changed_result()
        )

    monkeypatch.setattr(monitor_recheck_tasks, "_collect_inline", fake_collect)
    monkeypatch.setattr(monitor_recheck_tasks, "_finalize_recheck_state", lambda *a, **k: None)
    monkeypatch.setattr(
        monitor_recheck_tasks,
        "run_price_comparison",
        lambda *a, **k: comparison_calls.setdefault("called", True),
    )

    result = monitor_recheck_tasks.recheck_monitored_product.run(str(monitored_id))

    assert result == "completed"
    assert comparison_calls["called"] is True

def test_enqueue_due_monitored_respects_suspension(monkeypatch: pytest.MonkeyPatch):
    """Agendador deve ignorar execução quando suspensão global está ativa."""

    _, _, histogram, _, _ = _install_metric_mocks(monkeypatch)
    monkeypatch.setattr(monitor_recheck_tasks, "SessionLocal", lambda: DummySession())
    monkeypatch.setattr(monitor_recheck_tasks, "is_scraping_suspended", lambda: True)
    monkeypatch.setattr(monitor_recheck_tasks, "schedule_due_monitored", lambda db: 5)

    dispatched = monitor_recheck_tasks.enqueue_due_monitored.run()

    assert dispatched == 0
    assert histogram.calls, "histograma deve registrar a execução mesmo em suspensão"
        