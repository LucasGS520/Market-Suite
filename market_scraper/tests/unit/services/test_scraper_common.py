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

    async def is_allowed(self, *a, **k):
        return True

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

def _configura_orquestrador(monkeypatch, retorno: dict) -> None:


    class OrquestradorFalso:
        async def scrape(self, **_: dict) -> dict:
            return retorno

    monkeypatch.setattr(common, "MultiStrategyScraperOrchestrator", lambda *a, **k: OrquestradorFalso())
    monkeypatch.setattr(common.cache_manager, "get", lambda *a, **k: None)
    monkeypatch.setattr(common.cache_manager, "set", lambda *a, **k: None)

@pytest.mark.asyncio
async def test_scraper_product_common_async_success(monkeypatch):
    """ Deve retornar sucesso quando o orquestrador indica dados válidos """
    _configura_orquestrador(monkeypatch,{"status": "success", "details": {"current_price": "10"}})

    payload = SimpleNamespace(product_url="https://exemplo.com/item")
    resultado = await common.scrape_product_common_async(
        url="https://exemplo.com/item",
        user_id=uuid4(),
        payload=payload,
        product_type="monitored",
    )

    assert resultado["status"] == "success"
    assert resultado["details"]["current_price"] == "10"

@pytest.mark.asyncio
async def test_scrape_product_common_async_timeout(monkeypatch):
    """ Deve retornar erro quando a estratégia falha """

    _configura_orquestrador(monkeypatch, {"status": "error"})

    payload = SimpleNamespace(product_url="https://exemplo.com/item")
    resultado = await common.scrape_product_common_async(
        url="https://exemplo.com/item",
        user_id=uuid4(),
        payload=payload,
        product_type="monitored",
    )

    assert resultado["status"] == "error"

@pytest.mark.asyncio
async def test_scrape_product_common_async_html_not_product(monkeypatch):
    """ Retorna erro caso a página não pareça ser de produto """

    _configura_orquestrador(monkeypatch, {"status": "error"})

    payload = SimpleNamespace(product_url="https://exemplo.com/item")
    resultado = await common.scrape_product_common_async(
        url="https://exemplo.com/item",
        user_id=uuid4(),
        payload=payload,
        product_type="monitored",
    )

    assert resultado["status"] == "error"

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
    resultado = await common.scrape_product_common_async(
        url="https://exemplo.com/item",
        user_id=uuid4(),
        payload=payload,
        product_type="monitored",
    )

    assert resultado["status"] == "NOT_MODIFIED"
    assert StrategyShouldNotRun.called is False

@pytest.mark.asyncio
async def test_scrape_product_common_async_captcha_detected(monkeypatch):
    """ Retorna CAPTCHA quando o orquestrador detecta bloqueio """

    _configura_orquestrador(monkeypatch, {"status": BlockResult.CAPTCHA.value})

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
    """ Retorna erro quando o preço não é encontrado """

    _configura_orquestrador(monkeypatch, {"status": "error"})

    payload = SimpleNamespace(product_url="https://exemplo.com/item")
    resultado = await common.scrape_product_common_async(
        url="https://exemplo.com/item",
        user_id=uuid4(),
        payload=payload,
        product_type="monitored",
    )

    assert resultado["status"] == "error"

@pytest.mark.asyncio
async def test_scrape_product_common_async_not_modified(monkeypatch):
    """ Retorna NOT_MODIFIED quando o conteúdo não mudou """

    _configura_orquestrador(monkeypatch, {"status": "NOT_MODIFIED"})

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
            return SimpleNamespace(status_code=200, headers={"etag": "e1", "Last-Modified": "L1"})

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

@pytest.mark.asyncio
async def test_scrape_playwright_async_robots_forbidden(monkeypatch):
    url = "https://exemplo.com/proibido"

    class RobotsForbidden(DummyRobotsTxtParser):
        async def is_allowed(self, *a, **k):
            return False

    monkeypatch.setattr(common, "RobotsTxtParser", RobotsForbidden)
    monkeypatch.setattr(common, "ThrottleManager", DummyThrottleManager)
    monkeypatch.setattr(common, "HumanizedDelayManager", DummyHumanizedDelayManager)
    monkeypatch.setattr(common, "BlockRecoveryManager", DummyBlockRecoveryManager)
    monkeypatch.setattr(common, "CircuitBreaker", DummyCircuitBreaker)

    async def fake_get_html(*a, **k):
        raise AssertionError("_get_html não deve ser chamado")

    monkeypatch.setattr(common, "_get_html", fake_get_html)

    payload = SimpleNamespace(product_url=url)

    with pytest.raises(HTTPException) as exc:
        await common.scrape_playwright_async(
            url=url,
            user_id=uuid4(),
            payload=payload,
            product_type="monitored",
        )

    assert exc.value.status_code == status.HTTP_403_FORBIDDEN

@pytest.mark.asyncio
async def test_head_retry_after_suspends(monkeypatch):
    class DelayRecorder:
        def __init__(self):
            self.chamadas: list[float] = []

        async def wait_async(self, text, reflection_time: float = 1.0):
            self.chamadas.append(reflection_time)

    delay_recorder = DelayRecorder()

    class RecoveryOk(DummyBlockRecoveryManager):
        async def handle_block(self, *a, **k):
            return "<html>ok</html>"

    class Head429(DummyAsyncClient):
        async def head(self, *a, **k):
            return SimpleNamespace(status_code=429, headers={"Retry-After": "3"})

    monkeypatch.setattr(common, "HumanizedDelayManager", lambda: delay_recorder)
    monkeypatch.setattr(common, "ThrottleManager", DummyThrottleManager)
    monkeypatch.setattr(common, "BlockRecoveryManager", RecoveryOk)
    monkeypatch.setattr(common, "CircuitBreaker", DummyCircuitBreaker)
    monkeypatch.setattr(common, "RobotsTxtParser", DummyRobotsTxtParser)
    monkeypatch.setattr(common, "fetch_html_playwright", lambda url: (_ for _ in ()).throw(AssertionError("não deve ser chamado")))
    monkeypatch.setattr(common.httpx, "AsyncClient", Head429)
    monkeypatch.setattr(common, "get_cache_headers", lambda url: {"etag": None, "last_modified": None})
    monkeypatch.setattr(common, "store_cache_headers", lambda *a, **k: None)
    monkeypatch.setattr(common, "ContentSignature", DummySignature)

    async def fake_get_cached_html(url):
        return None

    async def fake_set_cached_html(*a, **k):
        return None

    monkeypatch.setattr(common, "get_cached_html", fake_get_cached_html)
    monkeypatch.setattr(common, "set_cached_html", fake_set_cached_html)
    monkeypatch.setattr(common.cache_manager, "get", lambda *a, **k: None)
    monkeypatch.setattr(common.cache_manager, "set", lambda *a, **k: None)
    monkeypatch.setattr(common.parser, "looks_like_product_page", lambda html: True)
    monkeypatch.setattr(common.parser, "parse_product_details", lambda html, url: {"name": "Produto", "current_price": "10"})

    payload = SimpleNamespace(product_url="https://exemplo.com/item")
    resultado = await common.scrape_product_common_async(
        url="https://exemplo.com/item",
        user_id=uuid4(),
        payload=payload,
        product_type="monitored",
    )

    assert resultado["status"] == "success"
    assert any(abs(c - 3) < 0.01 for c in delay_recorder.chamadas)

@pytest.mark.asyncio
async def test_get_html_backoff_reduz_taxa_apos_429(monkeypatch):
    class DummyThrottle:
        def __init__(self):
            self.rate = 1.0
            self.chamadas: list[int] = []

        async def wait_async(self, *a, **k):
            pass

        async def backoff_async(self, attempt: int, circuit_key: str):
            self.chamadas.append(attempt)
            self.rate *= 0.5

    throttle = DummyThrottle()

    async def fake_fetch_html(url):
        raise Exception("429")

    async def fake_get_cached_html(url):
        return None

    async def fake_set_cached_html(*a, **k):
        return None

    monkeypatch.setattr(common, "fetch_html_playwright", fake_fetch_html)
    monkeypatch.setattr(common, "get_cached_html", fake_get_cached_html)
    monkeypatch.setattr(common, "set_cached_html", fake_set_cached_html)
    monkeypatch.setattr(common, "cookie_manager", SimpleNamespace(get_cookies=lambda k: {}, update_from_response=lambda *a, **k: None))
    common._HTTP_429_ATTEMPTS.clear()

    params = dict(
        target_url="https://exemplo.com",
        circuit_key="ck",
        product_type="monitored",
        url_host="exemplo.com",
        throttle=throttle,
        human_delay=DummyHumanizedDelayManager(),
        circuit_breaker=DummyCircuitBreaker(),
        recovery_manager=DummyBlockRecoveryManager(),
    )

    with pytest.raises(HTTPException):
        await common._get_html(**params)

    taxa_primeira = throttle.rate
    assert taxa_primeira < 1.0
    assert throttle.chamadas == [1]
    assert common._HTTP_429_ATTEMPTS["ck"] == 1

    with pytest.raises(HTTPException):
        await common._get_html(**params)

    assert throttle.chamadas == [1, 2]
    assert throttle.rate < taxa_primeira
    assert common._HTTP_429_ATTEMPTS["ck"] == 2

    common._HTTP_429_ATTEMPTS.clear()
