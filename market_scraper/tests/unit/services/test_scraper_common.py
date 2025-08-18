import pytest
from types import SimpleNamespace
from uuid import uuid4
from fastapi import HTTPException, status

from market_scraper.services import services_scraper_common as common


class DummyThrottleManager:
    def __init__(self, *a, **k):
        pass

    async def wait_async(self, *a, **k):
        pass

class DummyHumanizedDelayManager:
    async def wait_async(self, *a, **k):
        pass

class DummyBlockRecoveryManager:
    def __init__(self, *a, **k):
        pass

    async def handle_block(self, *a, **k):
        return None


class DummyCircuitBreaker:
    def allow_request(self, *a, **k):
        return True

    def record_success(self, *a, **k):
        pass

    def record_failure(self, *a, **k):
        pass

class DummyRobotsTxtParser:
    def __init__(self, *a, **k):
        pass

    async def get_crawl_delay(self, *a, **k):
        return None

@pytest.mark.asyncio
async def test_scrape_product_common_async_success(monkeypatch):
    async def fake_fetch_html(url):
        return "<html>ok</html>"

    monkeypatch.setattr(common, "fetch_html_playwright", fake_fetch_html)
    async def fake_get_cached_html(url):
        return None

    async def fake_set_cached_html(*a, **k):
        return None

    monkeypatch.setattr(common, "get_cached_html", fake_get_cached_html)
    monkeypatch.setattr(common, "set_cached_html", fake_set_cached_html)
    monkeypatch.setattr(common.parser, "looks_like_product_page", lambda html: True)
    monkeypatch.setattr(common.parser, "parse_product_details", lambda html, url: {"current_price": "10"})
    monkeypatch.setattr(common, "ThrottleManager", DummyThrottleManager)
    monkeypatch.setattr(common, "HumanizedDelayManager", DummyHumanizedDelayManager)
    monkeypatch.setattr(common, "BlockRecoveryManager", DummyBlockRecoveryManager)
    monkeypatch.setattr(common, "CircuitBreaker", DummyCircuitBreaker)
    monkeypatch.setattr(common, "RobotsTxtParser", DummyRobotsTxtParser)

    payload = SimpleNamespace(product_url="https://exemplo.com/item")
    result = await common.scrape_product_common_async(
        url="https://exemplo.com/item",
        user_id=uuid4(),
        payload=payload,
        product_type="monitored",
    )

    assert result["status"] == "success"
    assert result["details"]["current_price"] == "10"

@pytest.mark.asyncio
async def test_scrape_product_common_async_timeout(monkeypatch):
    async def fake_fetch_html(url):
        raise common.PlaywrightTimeoutError("timeout")

    monkeypatch.setattr(common, "fetch_html_playwright", fake_fetch_html)
    async def fake_get_cached_html(url):
        return None

    async def fake_set_cached_html(*a, **k):
        return None

    monkeypatch.setattr(common, "get_cached_html", fake_get_cached_html)
    monkeypatch.setattr(common, "set_cached_html", fake_set_cached_html)
    monkeypatch.setattr(common, "ThrottleManager", DummyThrottleManager)
    monkeypatch.setattr(common, "HumanizedDelayManager", DummyHumanizedDelayManager)
    monkeypatch.setattr(common, "BlockRecoveryManager", DummyBlockRecoveryManager)
    monkeypatch.setattr(common, "CircuitBreaker", DummyCircuitBreaker)
    monkeypatch.setattr(common, "RobotsTxtParser", DummyRobotsTxtParser)

    payload = SimpleNamespace(product_url="https://exemplo.com/item")
    with pytest.raises(HTTPException) as exc:
        await common.scrape_product_common_async(
            url="https://exemplo.com/item",
            user_id=uuid4(),
            payload=payload,
            product_type="monitored",
        )

    assert exc.value.status_code == status.HTTP_502_BAD_GATEWAY

@pytest.mark.asyncio
async def test_scrape_product_common_async_html_not_product(monkeypatch):
    async def fake_get_cached_html(url):
        return "<html>lista</html>"

    async def fake_set_cached_html(*a, **k):
        return None

    async def fake_fetch_html(url):
        raise AssertionError("fetch_html_playwright não deve ser chamado")

    monkeypatch.setattr(common, "get_cached_html", fake_get_cached_html)
    monkeypatch.setattr(common, "set_cached_html", fake_set_cached_html)
    monkeypatch.setattr(common, "fetch_html_playwright", fake_fetch_html)

    monkeypatch.setattr(common, "looks_like_product_page", lambda html: False)

    def fake_parse_product_details(html, url):
        raise AssertionError("parse_product_details não deve ser chamado")

    monkeypatch.setattr(common.parser, "parse_product_details", fake_parse_product_details)
    monkeypatch.setattr(common, "ThrottleManager", DummyThrottleManager)
    monkeypatch.setattr(common, "HumanizedDelayManager", DummyHumanizedDelayManager)
    monkeypatch.setattr(common, "BlockRecoveryManager", DummyBlockRecoveryManager)
    monkeypatch.setattr(common, "CircuitBreaker", DummyCircuitBreaker)
    monkeypatch.setattr(common, "RobotsTxtParser", DummyRobotsTxtParser)

    payload = SimpleNamespace(product_url="https://exemplo.com/item")

    with pytest.raises(HTTPException) as exc:
        await common.scrape_product_common_async(
            url="https://exemplo.com/item",
            user_id=uuid4(),
            payload=payload,
            product_type="monitored",
        )

    assert exc.value.status_code == status.HTTP_400_BAD_REQUEST

@pytest.mark.asyncio
async def test_scrape_product_common_async_captcha_detected(monkeypatch):
    async def fake_get_cached_html(url):
        return "<html>captcha</html>"

    async def fake_set_cached_html(*a, **k):
        return None

    async def fake_fetch_html(url):
        return "<html>captcha</html>"

    monkeypatch.setattr(common, "get_cached_html", fake_get_cached_html)
    monkeypatch.setattr(common, "set_cached_html", fake_set_cached_html)
    monkeypatch.setattr(common, "fetch_html_playwright", fake_fetch_html)

    monkeypatch.setattr(common.parser, "looks_like_product_page", lambda html: True)

    def fake_parse_product_details(html, url):
        raise common.CaptchaDetectedError("captcha")

    monkeypatch.setattr(common.parser, "parse_product_details", fake_parse_product_details)
    monkeypatch.setattr(common, "ThrottleManager", DummyThrottleManager)
    monkeypatch.setattr(common, "HumanizedDelayManager", DummyHumanizedDelayManager)
    monkeypatch.setattr(common, "BlockRecoveryManager", DummyBlockRecoveryManager)
    monkeypatch.setattr(common, "CircuitBreaker", DummyCircuitBreaker)
    monkeypatch.setattr(common, "RobotsTxtParser", DummyRobotsTxtParser)

    payload = SimpleNamespace(product_url="https://exemplo.com/item")
    resultado = await common.scrape_product_common_async(
        url="https://exemplo.com/item",
        user_id=uuid4(),
        payload=payload,
        product_type="monitored",
    )

    assert resultado == {"status": "captcha"}

@pytest.mark.asyncio
async def test_scrape_product_common_async_not_price(monkeypatch):
    async def fake_get_cached_html(url):
        return "<html>produtos</html>"

    async def fake_set_cached_html(*a, **k):
        return None

    async def fake_fetch_html(url):
        return "<html>produto</html>"

    monkeypatch.setattr(common, "get_cached_html", fake_get_cached_html)
    monkeypatch.setattr(common, "set_cached_html", fake_set_cached_html)
    monkeypatch.setattr(common, "fetch_html_playwright", fake_fetch_html)

    monkeypatch.setattr(common.parser, "looks_like_product_page", lambda html: True)

    def fake_parse_product_details(html, url):
        return {"current_price": None}

    monkeypatch.setattr(common.parser, "parse_product_details", fake_parse_product_details)
    monkeypatch.setattr(common, "ThrottleManager", DummyThrottleManager)
    monkeypatch.setattr(common, "HumanizedDelayManager", DummyHumanizedDelayManager)
    monkeypatch.setattr(common, "BlockRecoveryManager", DummyBlockRecoveryManager)
    monkeypatch.setattr(common, "CircuitBreaker", DummyCircuitBreaker)
    monkeypatch.setattr(common, "RobotsTxtParser", DummyRobotsTxtParser)

    payload = SimpleNamespace(product_url="https://exemplo.com/item")

    with pytest.raises(HTTPException) as exc:
        await common.scrape_product_common_async(
            url="https://exemplo.com/item",
            user_id=uuid4(),
            payload=payload,
            product_type="monitored",
        )

    assert exc.value.status_code == status.HTTP_400_BAD_REQUEST
