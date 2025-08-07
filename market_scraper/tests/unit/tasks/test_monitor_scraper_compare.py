import importlib
from types import SimpleNamespace

class DummyGauge:
    def __init__(self):
        self.values = []
        self.inc_calls = 0
        self.dec_calls = 0

    def labels(self, **k):
        return self

    def observe(self, value):
        self.values.append(value)

    def set(self, value):
        self.values.append(value)

    def inc(self):
        self.inc_calls += 1

    def dec(self):
        self.dec_calls += 1

class DummySession:
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        pass


def test_compare_prices_task_records_metrics(monkeypatch):
    module = importlib.reload(importlib.import_module("alert_app.tasks.compare_prices_tasks"))
    gauge = DummyGauge()
    monkeypatch.setattr(module, "SCRAPING_LATENCY_SECONDS", gauge)
    monkeypatch.setattr(module, "SessionLocal", lambda: DummySession())
    monkeypatch.setattr(module, "redis_client", SimpleNamespace(set=lambda *a, **k: None))
    monkeypatch.setattr(module, "run_price_comparison", lambda db, mid, tolerance=None, price_change_threshold=None: (
            {"lowest_competitor": 1, "highest_competitor": 2}, ["a"]
        ),
    )
    captured = {}
    class DummySend:
        @staticmethod
        def delay(mid, alerts):
            captured["args"] = (mid, alerts)
    monkeypatch.setattr(module, "send_notification_task", DummySend)
    uid = "123e4567-e89b-12d3-a456-426614174000"
    module.compare_prices_task.run(uid)
    assert captured["args"] == (uid, ["a"])
    assert gauge.values

def test_collect_product_rate_limited(monkeypatch):
    module = importlib.reload(importlib.import_module("alert_app.tasks.scraper_tasks"))
    gauge = DummyGauge()
    inflight = DummyGauge()
    monkeypatch.setattr(module, "SCRAPING_LATENCY_SECONDS", gauge)
    monkeypatch.setattr(module, "SCRAPER_IN_FLIGHT", inflight)
    monkeypatch.setattr(module.circuit_breaker, "allow_request", lambda *a, **k: True)
    monkeypatch.setattr(module.RateLimiter, "allow_request", lambda self: False)
    module.collect_product_task.run("url", "u", "n", 1.0)
    assert inflight.dec_calls == 1
    assert gauge.values

def test_collect_competitor_circuit_breaker(monkeypatch):
    module = importlib.reload(importlib.import_module("alert_app.tasks.scraper_tasks"))
    gauge = DummyGauge()
    inflight = DummyGauge()
    monkeypatch.setattr(module, "SCRAPING_LATENCY_SECONDS", gauge)
    monkeypatch.setattr(module, "SCRAPER_IN_FLIGHT", inflight)
    monkeypatch.setattr(module.circuit_breaker, "allow_request", lambda *a, **k: False)
    monkeypatch.setattr(module.RateLimiter,"allow_request", lambda self: True)
    module.collect_competitor_task.run("m1", "url")
    assert inflight.dec_calls == 1
    assert gauge.values
