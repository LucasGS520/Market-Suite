from types import SimpleNamespace
from app.utils.adaptive_recheck import AdaptiveRecheckManager

def test_schedule_next_performance(benchmark, patch_rate_limiter):
    manager = AdaptiveRecheckManager()
    product = SimpleNamespace(id="prod1", target_price="100.00")
    benchmark(manager.schedule_next, product, [])
