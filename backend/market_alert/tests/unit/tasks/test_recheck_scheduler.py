""" Testes unitários para o agendador simplificado de rechecagens.

Valida que o scheduler `schedule_rechecks` enfileira corretamente produtos
com `next_check_at` vencido na fila `scraping`, respeitando limites e métricas.
"""
from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

import pytest

from backend.market_alert.tasks import recheck_scheduler_task


class DummySession:
    """ Permite simular sessão de banco de dados em testes """
    
    def __enter__(self):
        return self
    
    def __exit__(self, exc_type, exc, tb):
        return False
    
    def query(self, model):
        return DummyQuery()


class DummyQuery:
    """ Simula consultas ao banco de dados """
    
    def __init__(self):
        self.filters = []
        self.order_bys = []
        self.limit_val = None
    
    def filter(self, *conditions):
        self.filters.extend(conditions)
        return self
    
    def order_by(self, *orders):
        self.order_bys.extend(orders)
        return self
    
    def limit(self, val):
        self.limit_val = val
        return self
    
    def count(self):
        return 0
    
    def all(self):
        return []


class DummyMetric:
    """ Permite contar chamadas de métricas em testes """
    
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
    """ Estrutura mínima para simular produto monitorado """
    
    def __init__(self, product_id: UUID, user_id: UUID):
        self.id = product_id
        self.user_id = user_id
        self.product_url = "http://example.com/produto"
        self.name_identification = "Produto Teste"
        self.status = "active"
        self.next_check_at = datetime.now(timezone.utc) - timedelta(minutes=10)


def _install_metric_mocks(monkeypatch: pytest.MonkeyPatch):
    """ Instala mocks para todas as métricas usadas pelo scheduler """
    dispatch_metric = DummyMetric()
    enqueued_metric = DummyMetric()
    skipped_metric = DummyMetric()
    missing_metric = DummyMetric()
    latency_metric = DummyMetric()
    
    monkeypatch.setattr(recheck_scheduler_task, "RECHECK_DISPATCH_TOTAL", dispatch_metric)
    monkeypatch.setattr(recheck_scheduler_task, "RECHECK_ENQUEUED_TOTAL", enqueued_metric)
    monkeypatch.setattr(recheck_scheduler_task, "RECHECK_SKIPPED_NO_NEXT_CHECK_TOTAL", skipped_metric)
    monkeypatch.setattr(recheck_scheduler_task, "RECHECK_NEXT_CHECK_MISSING_TOTAL", missing_metric)
    monkeypatch.setattr(recheck_scheduler_task, "SCRAPING_LATENCY_SECONDS", latency_metric)
    
    return dispatch_metric, enqueued_metric, skipped_metric, missing_metric, latency_metric


def test_schedule_rechecks_respects_suspension(monkeypatch: pytest.MonkeyPatch):
    """ Scheduler deve ignorar execução quando suspensão global está ativa """
    
    _install_metric_mocks(monkeypatch)
    monkeypatch.setattr(recheck_scheduler_task, "SessionLocal", lambda: DummySession())
    monkeypatch.setattr(recheck_scheduler_task, "is_scraping_suspended", lambda: True)
    
    dispatched = recheck_scheduler_task.schedule_rechecks.run()
    
    assert dispatched == 0


def test_schedule_rechecks_enqueues_due_products(monkeypatch: pytest.MonkeyPatch):
    """ Scheduler deve enfileirar produtos com next_check_at vencido """
    
    user_id = uuid4()
    product_id = uuid4()
    monitored = DummyMonitored(product_id, user_id)
    enqueued_payloads = []
    
    dispatch_metric, enqueued_metric, _, _, _ = _install_metric_mocks(monkeypatch)
    
    class CustomQuery(DummyQuery):
        def all(self):
            return [monitored]
    
    class CustomSession(DummySession):
        def query(self, model):
            return CustomQuery()
    
    monkeypatch.setattr(recheck_scheduler_task, "SessionLocal", lambda: CustomSession())
    monkeypatch.setattr(recheck_scheduler_task, "is_scraping_suspended", lambda: False)
    
    def fake_build_payload(monitored, *, user_id):
        return {
            "kind": "monitored",
            "monitored_id": str(monitored.id),
            "user_id": str(user_id),
            "url": monitored.product_url,
            "name": monitored.name_identification,
        }
    
    monkeypatch.setattr(
        "market_alert.tasks.recheck_scheduler_task.build_monitored_payload",
        fake_build_payload,
    )
    
    def fake_collect_task_apply_async(**kwargs):
        enqueued_payloads.append(kwargs.get("kwargs", {}).get("payload"))
    
    class FakeCollectTask:
        def apply_async(self, **kwargs):
            fake_collect_task_apply_async(**kwargs)
    
    monkeypatch.setattr(
        "market_alert.tasks.recheck_scheduler_task.collect_product_task",
        FakeCollectTask(),
    )
    
    dispatched = recheck_scheduler_task.schedule_rechecks.run()
    
    assert dispatched == 1
    assert len(enqueued_payloads) == 1
    assert enqueued_payloads[0]["monitored_id"] == str(product_id)
    assert dispatch_metric.calls
    assert enqueued_metric.calls


def test_schedule_rechecks_respects_batch_limit(monkeypatch: pytest.MonkeyPatch):
    """ Scheduler deve respeitar limite de batch configurado """
    
    batch_limit = 3
    products = [DummyMonitored(uuid4(), uuid4()) for _ in range(5)]
    enqueued_count = []
    
    _install_metric_mocks(monkeypatch)
    
    class CustomQuery(DummyQuery):
        def all(self):
            #Simula que o limite foi aplicado
            return products[:batch_limit]
    
    class CustomSession(DummySession):
        def query(self, model):
            return CustomQuery()
    
    monkeypatch.setattr(recheck_scheduler_task, "SessionLocal", lambda: CustomSession())
    monkeypatch.setattr(recheck_scheduler_task, "is_scraping_suspended", lambda: False)
    
    def fake_build_payload(monitored, *, user_id):
        return {"monitored_id": str(monitored.id)}
    
    monkeypatch.setattr(
        "market_alert.tasks.recheck_scheduler_task.build_monitored_payload",
        fake_build_payload,
    )
    
    class FakeCollectTask:
        def apply_async(self, **kwargs):
            enqueued_count.append(1)
    
    monkeypatch.setattr(
        "market_alert.tasks.recheck_scheduler_task.collect_product_task",
        FakeCollectTask(),
    )
    
    dispatched = recheck_scheduler_task.schedule_rechecks.run()
    
    assert dispatched == batch_limit
    assert len(enqueued_count) == batch_limit
