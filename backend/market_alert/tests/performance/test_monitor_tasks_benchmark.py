import time
from uuid import uuid4
from types import SimpleNamespace

from backend.market_alert.tasks import monitor_recheck_tasks


def test_collect_inline_benchmark(benchmark, monkeypatch):
    """Garante que a coleta inline permanece leve com o dispatcher atual."""

    def fake_collect_product(payload, **_kwargs):
        time.sleep(0.05)
        return "success", SimpleNamespace(price_changed=True, availability_changed=False)

    monkeypatch.setattr(monitor_recheck_tasks, "collect_product", fake_collect_product)

    payload = {"monitored_id": str(uuid4()), "url": "http://exemplo.com/produto"}

    def run():
        start = time.perf_counter()
        outcome = monitor_recheck_tasks._collect_inline(
            payload,
            product_id=uuid4(),
            kind="monitored",
            logger_bound=None,
        )
        return time.perf_counter() - start, outcome

    tempo_execucao, outcome = benchmark(run)
    assert tempo_execucao < 0.1
    assert outcome.status == "success"
    assert outcome.price_changed is True

def test_compute_next_check_at_benchmark(benchmark):
    """Valida cálculo rápido de próxima janela de rechecagem."""

    monitored = SimpleNamespace(check_interval=30)
    reference = monitor_recheck_tasks.datetime.now(monitor_recheck_tasks.timezone.utc)

    tempo_execucao = benchmark(lambda: monitor_recheck_tasks._compute_next_check_at(monitored, reference))

    assert tempo_execucao == reference + monitor_recheck_tasks.timedelta(seconds=30)
