import pytest
from types import SimpleNamespace
from uuid import uuid4

from aiohttp import payload_type
from celery.bin.result import result
from fastapi import HTTPException, status

from market_scraper.services import services_scraper_common as common
from shared.enums import BlockResult


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

class DummyAsyncClient:
    def __init__(self, *a, **k):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a, **k):
        pass

    async def head(self, *a, **k):
        return SimpleNamespace(status_code=200, headers={})

class DummySignature:
    def __init__(self, *a, **k):
        pass

    def check_or_update(self, html):
        return "assinatura"

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
    monkeypatch.setattr(common.cache_manager, "get", lambda *a, **k: None)
    monkeypatch.setattr(common.cache_manager, "set", lambda *a, **k: None)
    monkeypatch.setattr(common.parser, "looks_like_product_page", lambda html: True)
    monkeypatch.setattr(common.parser, "parse_product_details", lambda html, url: {"current_price": "10"})
    monkeypatch.setattr(common, "ThrottleManager", DummyThrottleManager)
    monkeypatch.setattr(common, "HumanizedDelayManager", DummyHumanizedDelayManager)
    monkeypatch.setattr(common, "BlockRecoveryManager", DummyBlockRecoveryManager)
    monkeypatch.setattr(common, "CircuitBreaker", DummyCircuitBreaker)
    monkeypatch.setattr(common, "RobotsTxtParser", DummyRobotsTxtParser)
    monkeypatch.setattr(common, "get_cache_headers", lambda url: {"etag": None, "last_modified": None})
    monkeypatch.setattr(common, "store_cache_headers", lambda *a, **k: None)
    monkeypatch.setattr(common.httpx, "AsyncClient", DummyAsyncClient)
    monkeypatch.setattr(common, "ContentSignature", DummySignature)

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
    monkeypatch.setattr(common.cache_manager, "get", lambda *a, **k: None)
    monkeypatch.setattr(common.cache_manager, "set", lambda *a, **k: None)
    monkeypatch.setattr(common, "ThrottleManager", DummyThrottleManager)
    monkeypatch.setattr(common, "HumanizedDelayManager", DummyHumanizedDelayManager)
    monkeypatch.setattr(common, "BlockRecoveryManager", DummyBlockRecoveryManager)
    monkeypatch.setattr(common, "CircuitBreaker", DummyCircuitBreaker)
    monkeypatch.setattr(common, "RobotsTxtParser", DummyRobotsTxtParser)
    monkeypatch.setattr(common, "get_cache_headers", lambda url: {"etag": None, "last_modified": None})
    monkeypatch.setattr(common, "store_cache_headers", lambda *a, **k: None)
    monkeypatch.setattr(common.httpx, "AsyncClient", DummyAsyncClient)
    monkeypatch.setattr(common, "ContentSignature", DummySignature)

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
    monkeypatch.setattr(common.cache_manager, "get", lambda *a, **k: None)
    monkeypatch.setattr(common.cache_manager, "set", lambda *a, **k: None)
    monkeypatch.setattr(common, "fetch_html_playwright", fake_fetch_html)

    monkeypatch.setattr(common.parser, "looks_like_product_page", lambda html: False)

    def fake_parse_product_details(html, url):
        raise AssertionError("parse_product_details não deve ser chamado")

    monkeypatch.setattr(common.parser, "parse_product_details", fake_parse_product_details)
    monkeypatch.setattr(common, "ThrottleManager", DummyThrottleManager)
    monkeypatch.setattr(common, "HumanizedDelayManager", DummyHumanizedDelayManager)
    monkeypatch.setattr(common, "BlockRecoveryManager", DummyBlockRecoveryManager)
    monkeypatch.setattr(common, "CircuitBreaker", DummyCircuitBreaker)
    monkeypatch.setattr(common, "RobotsTxtParser", DummyRobotsTxtParser)
    monkeypatch.setattr(common, "get_cache_headers", lambda url: {"etag": None, "last_modified": None})
    monkeypatch.setattr(common, "store_cache_headers", lambda *a, **k: None)
    monkeypatch.setattr(common.httpx, "AsyncClient", DummyAsyncClient)
    monkeypatch.setattr(common, "ContentSignature", DummySignature)

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
async def test_scrape_product_common_async_not_modified_breaks(monkeypatch):
    class StrategyNotModified:
        def supports_url(self, url):
            return True

        async def get_data(
            self,
            *,
            url,
            headers,
            user_id,
            payload,
            product_type,
            rate_limiter,
            circuit_breaker,
            recovery_manager,
        ):
            return {"status": "NOT_MODIFIED"}

    class StrategyShouldNotRun:
        called = False

        def supports_url(self, url):
            return True

        async def get_data(
            self,
            *,
            url,
            headers,
            user_id,
            payload,
            product_type,
            rate_limiter,
            circuit_breaker,
            recovery_manager,
        ):
            StrategyShouldNotRun.called = True
            return {"status": "success", "details": {"ok": True}}

    #Evita retorno imediato de cache
    monkeypatch.setattr(common.cache_manager, "get", lambda *a, **k: None)
    monkeypatch.setattr(common.cache_manager, "set", lambda *a, **k: None)

    #Força o uso das estratégias fictícias
    monkeypatch.setattr(common, "strategies_for", lambda url: [StrategyNotModified(), StrategyShouldNotRun()])

    payload = SimpleNamespace(product_url="https://exemplo.com/item")

    result = await common.scrape_product_common_async(
        url="https://exemplo.com/item",
        user_id=uuid4(),
        payload=payload,
        product_type="monitored",
    )

    assert result["status"] == "NOT_MODIFIED"
    assert StrategyShouldNotRun.called is False

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
    monkeypatch.setattr(common.cache_manager, "get", lambda *a, **k: None)
    monkeypatch.setattr(common.cache_manager, "set", lambda *a, **k: None)
    monkeypatch.setattr(common, "fetch_html_playwright", fake_fetch_html)

    monkeypatch.setattr(common.parser, "looks_like_product_page", lambda html: True)

    def fake_parse_product_details(html, url):
        raise common.CaptchaDetectedError(BlockResult.CAPTCHA.value)

    monkeypatch.setattr(common.parser, "parse_product_details", fake_parse_product_details)
    monkeypatch.setattr(common, "ThrottleManager", DummyThrottleManager)
    monkeypatch.setattr(common, "HumanizedDelayManager", DummyHumanizedDelayManager)
    monkeypatch.setattr(common, "BlockRecoveryManager", DummyBlockRecoveryManager)
    monkeypatch.setattr(common, "CircuitBreaker", DummyCircuitBreaker)
    monkeypatch.setattr(common, "RobotsTxtParser", DummyRobotsTxtParser)
    monkeypatch.setattr(common, "get_cache_headers", lambda url: {"etag": None, "last_modified": None})
    monkeypatch.setattr(common, "store_cache_headers", lambda *a, **k: None)
    monkeypatch.setattr(common.httpx, "AsyncClient", DummyAsyncClient)
    monkeypatch.setattr(common, "ContentSignature", DummySignature)

    payload = SimpleNamespace(product_url="https://exemplo.com/item")
    resultado = await common.scrape_product_common_async(
        url="https://exemplo.com/item",
        user_id=uuid4(),
        payload=payload,
        product_type="monitored",
    )

    assert resultado == {"status": BlockResult.CAPTCHA.value}

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
    monkeypatch.setattr(common.cache_manager, "get", lambda *a, **k: None)
    monkeypatch.setattr(common.cache_manager, "set", lambda *a, **k: None)
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
    monkeypatch.setattr(common, "get_cache_headers", lambda url: {"etag": None, "last_modified": None})
    monkeypatch.setattr(common, "store_cache_headers", lambda *a, **k: None)
    monkeypatch.setattr(common.httpx, "AsyncClient", DummyAsyncClient)
    monkeypatch.setattr(common, "ContentSignature", DummySignature)

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
async def test_scrape_product_common_async_not_modified(monkeypatch):
    class Head304(DummyAsyncClient):
        async def head(self, *a, **k):
            return SimpleNamespace(status_code=304, headers={})

    monkeypatch.setattr(common.httpx, "AsyncClient", Head304)
    monkeypatch.setattr(common, "get_cache_headers", lambda url: {"etag": "x", "last_modified": "y"})
    monkeypatch.setattr(common, "store_cache_headers", lambda *a, **k: None)
    async def fake_fetch_html(url):
        raise AssertionError("fetch_html_playwright não deve ser chamado")
    monkeypatch.setattr(common, "fetch_html_playwright", fake_fetch_html)
    monkeypatch.setattr(common.cache_manager, "get", lambda *a, **k: None)
    monkeypatch.setattr(common.cache_manager, "set", lambda *a, **k: None)
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
    assert resultado == {"status": "NOT_MODIFIED"}

@pytest.mark.asyncio
async def test_scrape_playwright_async_not_modified_on_304(monkeypatch, fake_redis):
    url = "https://exemplo.com/item"
    #Preenche o Redis com cabeçalhos previamente armazenados
    common.store_cache_headers(url, etag="e1", last_modified="L1")

    capturado = {}

    class Head304:
        def __init__(self, *a, **k):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a, **k):
            pass

        async def head(self, url, headers=None, cookies=None):
            capturado["headers"] = headers
            return SimpleNamespace(status_code=304, headers={})

    monkeypatch.setattr(common.httpx, "AsyncClient", Head304)

    async def fake_fetch_html(url):
        raise AssertionError("fetch_html_playwright não deve ser chamado")

    async def fake_parse_html(*a, **k):
        raise AssertionError("_parse_html não deve ser chamado")

    monkeypatch.setattr(common, "fetch_html_playwright", fake_fetch_html)
    monkeypatch.setattr(common, "_parse_html", fake_parse_html)
    monkeypatch.setattr(common, "ThrottleManager", DummyThrottleManager)
    monkeypatch.setattr(common, "HumanizedDelayManager", DummyHumanizedDelayManager)
    monkeypatch.setattr(common, "BlockRecoveryManager", DummyBlockRecoveryManager)
    monkeypatch.setattr(common, "CircuitBreaker", DummyCircuitBreaker)
    monkeypatch.setattr(common, "RobotsTxtParser", DummyRobotsTxtParser)

    payload = SimpleNamespace(product_url=url)
    resultado = await common.scrape_playwright_async(
        url=url,
        user_id=uuid4(),
        payload=payload,
        product_type="monitored",
    )

    assert resultado == {"status": "NOT_MODIFIED"}
    assert capturado["headers"].get("If-None-Match") == "e1"
    assert capturado["headers"].get("If-Modified-Since") == "L1"
    assert "User-Agent" in capturado["headers"]
    headers = common.get_cache_headers(url)
    assert headers["etag"] == "e1"
    assert headers["last_modified"] == "L1"

@pytest.mark.asyncio
async def test_scrape_playwright_async_signature_skips_parsing(monkeypatch, fake_redis):
    url = "https://exemplo.com/item"
    html = "<html>produto</html>"

    #Assinatura e cabeçalhos gravados previamente em Redis
    common.store_cache_headers(url, etag="e1", last_modified="L1")
    assinante = common.ContentSignature(url)
    assinante.update(html)

    cache_html: dict[str, str] = {url: html}

    async def fake_get_cached_html(u):
        return cache_html.get(u)

    async def fake_set_cached_html(u, h):
        cache_html[u] = h

    async def fake_fetch_html(url):
        raise AssertionError("fetch_html_playwright não deve ser chamado")

    async def fake_parse_html(*a, **k):
        raise AssertionError("_parse_html não deve ser chamado")

    capturado = {}

    class Head200:
        def __init__(self, *a, **k):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a, **k):
            pass

        async def head(self, url, headers=None, cookies=None):
            capturado["headers"] = headers
            return SimpleNamespace(status_code=200, headers={"etag": "e1", "last_modified": "L1"})

    monkeypatch.setattr(common.httpx, "AsyncClient", Head200)
    monkeypatch.setattr(common, "get_cached_html", fake_get_cached_html)
    monkeypatch.setattr(common, "set_cached_html", fake_set_cached_html)
    monkeypatch.setattr(common, "fetch_html_playwright", fake_fetch_html)
    monkeypatch.setattr(common, "_parse_html", fake_parse_html)
    monkeypatch.setattr(common, "ThrottleManager", DummyThrottleManager)
    monkeypatch.setattr(common, "HumanizedDelayManager", DummyHumanizedDelayManager)
    monkeypatch.setattr(common, "BlockRecoveryManager", DummyBlockRecoveryManager)
    monkeypatch.setattr(common, "CircuitBreaker", DummyCircuitBreaker)
    monkeypatch.setattr(common, "RobotsTxtParser", DummyRobotsTxtParser)

    payload = SimpleNamespace(product_url=url)
    resultado = await common.scrape_playwright_async(
        url=url,
        user_id=uuid4(),
        payload=payload,
        product_type="monitored",
    )

    assert resultado == {"status": "NOT_MODIFIED"}
    assert capturado["headers"].get("If-None-Match") == "e1"
    assert capturado["headers"].get("If-Modified-Since") == "L1"
    assert "User-Agent" in capturado["headers"]
    assert assinante.get() == assinante.calculate(html)
