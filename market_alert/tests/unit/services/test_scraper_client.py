import pytest
import httpx

from market_alert.services.scraper_client import ScraperClient, ScraperClientError


class DummyClientSuccess:
    def __init__(self, *a, **k):
        pass

    async def post(self, url, json):
        return httpx.Response(200, json={"ok": True}, request=httpx.Request("POST", url))

    async def aclose(self):
        pass

    
class DummyClientErro(DummyClientSuccess):
    async def post(self, url, json):
        return httpx.Response(422, json={}, request=httpx.Request("POST", url))

class DummyClientTimeout(DummyClientSuccess):
    async def post(self, url, json):
        raise httpx.TimeoutException("timeout", request=httpx.Request("POST", url))


@pytest.mark.asyncio
async def test_parse_success(monkeypatch):
    monkeypatch.setattr("market_alert.services.scraper_client.httpx.AsyncClient", DummyClientSuccess)
    cliente = ScraperClient(base_url="http://fake")
    resultado = await cliente.parse("http://url", "monitored")
    assert resultado == {"ok": True}
    await cliente.aclose()

@pytest.mark.asyncio
async def test_parse_erro_http(monkeypatch):
    monkeypatch.setattr("market_alert.services.scraper_client.httpx.AsyncClient", DummyClientErro)
    cliente = ScraperClient(base_url="http://fake")
    with pytest.raises(ScraperClientError) as exc:
        await cliente.parse("http://url", "monitored")
    assert exc.value.status_code == 422
    await cliente.aclose()

@pytest.mark.asyncio
async def test_parse_timeout(monkeypatch):
    monkeypatch.setattr("market_alert.services.scraper_client.httpx.AsyncClient", DummyClientTimeout)
    cliente = ScraperClient(base_url="http://fake")
    with pytest.raises(ScraperClientError):
        await cliente.parse("http://url", "monitored")
    await cliente.aclose()
