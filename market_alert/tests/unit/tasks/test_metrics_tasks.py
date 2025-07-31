from random import gauss
from types import SimpleNamespace
from app.tasks import metrics_tasks
from infra.db.database import checkout


class DummyGauge:
    def __init__(self):
        self.values = []

    def labels(self, **k):
        return self

    def set(self, value):
        self.values.append(value)

    def observe(self, value):
        self.values.append(value)


class FakeInspect:
    def reserved(self):
        return {"w1": [1]}

    def scheduled(self):
        return {"w1": [2]}

    def stats(self):
        return {"w1": {"pool": {"max-concurrency": 2}}}


class FakeRedis:
    def __init__(self):
        self.data = {"celery": [1, 2], "scraping": [], "monitor": []}

    def llen(self, key):
        return len(self.data.get(key, []))

    def info(self, section=None):
        return {"used_memory": 100}


class DummyLogger:
    def __init__(self):
        self.events = []

    def info(self, *a, **k):
        self.events.append(k)


def test_collect_celery_metrics(monkeypatch):
    fake_insp = FakeInspect()
    fake_redis = FakeRedis()
    gauges = DummyGauge()
    monkeypatch.setattr(metrics_tasks.celery_app.control, "inspect", lambda: fake_insp)
    monkeypatch.setattr(metrics_tasks, "redis_client", fake_redis)
    monkeypatch.setattr(metrics_tasks, "CELERY_QUEUE_LENGTH", gauges)
    monkeypatch.setattr(metrics_tasks, "REDIS_QUEUE_MESSAGES", gauges)
    monkeypatch.setattr(metrics_tasks, "REDIS_MEMORY_USAGE_BYTES", gauges)
    monkeypatch.setattr(metrics_tasks, "CELERY_WORKERS_TOTAL", gauges)
    monkeypatch.setattr(metrics_tasks, "CELERY_WORKER_CONCURRENCY", gauges)

    metrics_tasks.collect_celery_metrics()
    assert gauges.values

def test_collect_celery_metrics_logs_per_queue(monkeypatch):
    fake_insp = FakeInspect()
    fake_redis = FakeRedis()
    gauges = DummyGauge()
    dummy_logger = DummyLogger()

    monkeypatch.setattr(metrics_tasks.celery_app.control, "inspect", lambda: fake_insp)
    monkeypatch.setattr(metrics_tasks, "redis_client", fake_redis)
    monkeypatch.setattr(metrics_tasks, "CELERY_QUEUE_LENGTH", gauges)
    monkeypatch.setattr(metrics_tasks, "REDIS_QUEUE_MESSAGES", gauges)
    monkeypatch.setattr(metrics_tasks, "REDIS_MEMORY_USAGE_BYTES", gauges)
    monkeypatch.setattr(metrics_tasks, "CELERY_WORKERS_TOTAL", gauges)
    monkeypatch.setattr(metrics_tasks, "CELERY_WORKER_CONCURRENCY", gauges)
    monkeypatch.setattr(metrics_tasks, "logger", dummy_logger)

    metrics_tasks.collect_celery_metrics()

    queues = {e["queue"] for e in dummy_logger.events}
    assert len(dummy_logger.events) == 3
    assert queues == {"celery", "scraping", "monitor"}


def test_collect_db_metrics(monkeypatch):
    fake_engine = SimpleNamespace(pool=SimpleNamespace(size=lambda: 1, checkedout=lambda: 0))
    monkeypatch.setattr(metrics_tasks, "get_engine", lambda: fake_engine)
    gauges = DummyGauge()
    monkeypatch.setattr(metrics_tasks, "DB_POOL_SIZE", gauges)
    monkeypatch.setattr(metrics_tasks, "DB_POOL_CHECKOUTS", gauges)
    metrics_tasks.collect_db_metrics()
    assert gauges.values == [1, 0]
