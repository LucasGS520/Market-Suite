from app.utils.rate_limiter import RateLimiter

def test_rate_limiter_allow_request_performance(benchmark, patch_rate_limiter):
    limiter = RateLimiter(redis_key="rate:test", max_requests=10, window_seconds=1)
    benchmark(limiter.allow_request)
