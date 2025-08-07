from uuid import uuid4
from types import SimpleNamespace
from datetime import datetime, timezone, timedelta

from scraper_app.utils.adaptive_recheck import AdaptiveRecheckManager

def make_product(price=100):
    return SimpleNamespace(id=uuid4(), target_price=price)

def make_comparison(alert=False, avg=100, low=95):
    data = {
        "average_competitor_price": avg,
        "lowest_competitor": {"price": low},
        "alerts": [1] if alert else []
    }
    return SimpleNamespace(data=data)

def test_schedule_shorter_on_alert(patch_rate_limiter):
    mgr = AdaptiveRecheckManager(base_interval=100, min_interval=1)
    prod = make_product(100)
    cmp_ = make_comparison(alert=True, avg=100, low=95)
    now = datetime.now(timezone.utc)
    nxt = mgr.schedule_next(prod, [cmp_])
    assert (nxt - now).total_seconds() < 100

def test_backoff_on_failures(patch_rate_limiter):
    mgr = AdaptiveRecheckManager(base_interval=50, min_interval=1)
    prod = make_product(100)
    mgr.record_result(str(prod.id), False)
    first = mgr.schedule_next(prod)
    mgr.record_result(str(prod.id), False)
    second = mgr.schedule_next(prod)
    assert (second - datetime.now(timezone.utc)).total_seconds() > (
        first - datetime.now(timezone.utc)
    ).total_seconds()

def test_should_recheck(patch_rate_limiter):
    mgr = AdaptiveRecheckManager(base_interval=10, min_interval=1)
    prod = make_product()
    mgr.schedule_next(prod)
    assert not mgr.should_recheck(str(prod.id))
    past = datetime.now(timezone.utc) - timedelta(seconds=1)
    mgr.redis.set(mgr._next_key(str(prod.id)), past.isoformat())
    assert mgr.should_recheck(str(prod.id))
