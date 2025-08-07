import time
import random

from app.utils.throttle_manager import ThrottleManager


class DummyCB:
    def record_failure(self, *a, **k):
        pass

def test_throttle_wait_performance(benchmark, monkeypatch):
    monkeypatch.setattr(time, "sleep", lambda s: None)
    monkeypatch.setattr(random, "uniform", lambda a, b: 0.0)
    monkeypatch.setattr("alert_app.utils.throttle_manager.CircuitBreaker", lambda: DummyCB())

    tm = ThrottleManager(rate=1e6, capacity=1e6, jitter_range=(0.0, 0.0))
    benchmark(tm.wait, "cb")

def test_throttle_backoff_performance(benchmark, monkeypatch):
    monkeypatch.setattr(time, "sleep", lambda s: None)
    monkeypatch.setattr(random, "uniform", lambda a, b: 0.1)
    monkeypatch.setattr("alert_app.utils.throttle_manager.CircuitBreaker", lambda: DummyCB())

    tm = ThrottleManager(rate=10.0, capacity=10, jitter_range=(0.1, 0.1))
    benchmark(tm.backoff, 3, "cb")
