""" Testes unitários para a estratégia ShopeeJsonStrategy baseada em JSON """

import pytest
import httpx
import asyncio

from celery.bin.result import result

from market_scraper.strategies.json_endpoint import ShopeeJsonStrategy
from market_scraper.utils.intelligent_cache import IntelligentCacheManager


@pytest.fixture(autouse=True)
def limpar_cache(monkeypatch: pytest.MonkeyPatch) -> None:
    """ Reinicia o cache compartilhado antes de cada teste """
    monkeypatch.setattr("market_scraper.strategies.json_endpoint.cache_manager", IntelligentCacheManager())

@pytest.fixture
def strategy() -> ShopeeJsonStrategy:
    """ Instância da estratégia de API da Shopee """
    return ShopeeJsonStrategy()

class DummyResponse:
    """ Resposta falsa usada para simular retornos do ``httpx`` """

    def __init__(self, status_code: int = 200, json_data: dict | None = None) -> None:
        self.status_code = status_code
        self._json_data = json_data or {}
        self.text = ""

    def json(self) -> dict:
        return self._json_data

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise httpx.HTTPStatusError("erro", request=None, response=None)

@pytest.mark.asyncio
@pytest.mark.parametrize(
    "dados_preco",
    [
        {"price": 123456},
        {"price_min": 123456},
        {"price_max": 123456},
        {"price_before_discount": 123456},
        {"models": [{"price": 123456}]},
    ]
)
async def test_retorna_dados_em_caso_de_sucesso(monkeypatch: pytest.MonkeyPatch, strategy: ShopeeJsonStrategy, dados_preco: dict) -> None:
    """ Verifica fluxo completo retornado nome e preço a partir de diferentes campos """
    def fake_validate(self, data: dict) -> None:
        pass

    class DummyClient:
        """ Cliente assíncrono que simula duas chamadas consecutivas """
        def __init__(self, *a, **k) -> None:
            self.headers = k.get("headers", {})
            self.cookies: dict = {}

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            pass

        async def get(self, url: str, params: dict | None = None) -> DummyResponse:
            if "api/v4/item/get" in url:
                data = {"name": "Produto"}
                data.update(dados_preco)
                return DummyResponse(200, {"data": data})
            #Primeira chamada captura cookie CSRF
            self.cookies["csrftoken"] = "abc123"
            return DummyResponse(200)

    monkeypatch.setattr(httpx, "AsyncClient", DummyClient)
    monkeypatch.setattr("market_scraper.strategies.json_endpoint.DataQualityValidator.validate", fake_validate)

    resultado = await strategy.get_data("https://shopee.com.br/produto-i.1.2")
    detalhes = resultado["details"]
    assert resultado["status"] == "success"
    assert detalhes["name"] == "Produto"
    assert detalhes["current_price"] == "R$ 1,23"

@pytest.mark.asyncio
@pytest.mark.parametrize("status_code", [401, 403])
async def test_retorna_erro_em_falha_de_autenticacao(monkeypatch: pytest.MonkeyPatch, strategy: ShopeeJsonStrategy, status_code: int) -> None:
    """ Garante que respostas 401/403 resultam em ``{"status": "error"}`` """
    def fake_validate(self, data: dict) -> None:
        pass

    class DummyClient:
        def __init__(self, *a, **k) -> None:
            self.headers = k.get("headers", {})
            self.cookies: dict = {}

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            pass

        async def get(self, url: str, params: dict | None = None) -> DummyResponse:
            if "api/v4/item/get" in url:
                return DummyResponse(status_code)
            return DummyResponse(200)

    monkeypatch.setattr(httpx, "AsyncClient", DummyClient)
    monkeypatch.setattr("market_scraper.strategies.json_endpoint.DataQualityValidator.validate", fake_validate)

    resultado = await strategy.get_data("https://shopee.com.br/produto-i.1.2")
    assert resultado == {"status": "error"}

@pytest.mark.asyncio
async def test_retorna_erro_quando_json_invalido(monkeypatch: pytest.MonkeyPatch, strategy: ShopeeJsonStrategy) -> None:
    """ Assegura que JSON malformado resulte em ``{"status": "error"}`` """
    class InvalidResponse(DummyResponse):
        def json(self) -> dict:
            raise ValueError("invalid json")

    class DummyClient:
        def __init__(self, *a, **k) -> None:
            self.headers = k.get("headers", {})
            self.cookies: dict = {}

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            pass

        async def get(self, url: str, params: dict | None = None) -> DummyResponse:
            if "api/v4/item/get" in url:
                return InvalidResponse(200)
            self.cookies["csrftoken"] = "abc"
            return DummyResponse(200)

    monkeypatch.setattr(httpx, "AsyncClient", DummyClient)
    monkeypatch.setattr("market_scraper.strategies.json_endpoint.DataQualityValidator.validate", lambda self, data: None)

    resultado = await strategy.get_data("https://shopee.com.br/produto-i.1.2")
    assert resultado == {"status": "error"}

@pytest.mark.asyncio
async def test_realiza_retry_em_falha_temporaria(monkeypatch: pytest.MonkeyPatch, strategy: ShopeeJsonStrategy) -> None:
    """ Verifica se o backoff exponencial reexecuta chamadas em falhas transitórias """
    def fake_validate(self, data: dict) -> None:
        pass

    calls = {"count": 0}

    class DummyClient:
        """ Cliente que falha na primeira tentativa e depois retorna sucesso """
        def __init__(self, *a, **k) -> None:
            self.headers = k.get("headers", {})
            self.cookies: dict = {}

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            pass

        async def get(self, url: str, params: dict | None = None) -> DummyResponse:
            if "api/v4/item/get" in url:
                calls["count"] += 1
                if calls["count"] == 1:
                    return DummyResponse(500)
                data = {"name": "Produto", "price": 123456}
                return DummyResponse(200, {"data": data})
            return DummyResponse(200)

    async def fake_sleep(_: float) -> None:
        """ Evita esperar reais durante o backoff """
        return None

    monkeypatch.setattr(httpx, "AsyncClient", DummyClient)
    monkeypatch.setattr(asyncio, "sleep", fake_sleep)
    monkeypatch.setattr("market_scraper.strategies.json_endpoint.DataQualityValidator.validate", fake_validate)

    resultado = await strategy.get_data("https://shopee.com.br/produto-i.1.2")
    assert resultado["status"] == "success"
    assert calls["count"] == 2

@pytest.mark.asyncio
async def test_utiliza_cache_para_chamadas_repetidas(monkeypatch: pytest.MonkeyPatch, strategy: ShopeeJsonStrategy) -> None:
    """ Garante que respostas recentes sejam reutilizadas do cache """
    def fake_validate(self, data: dict) -> None:
        pass

    cache = IntelligentCacheManager()

    class DummyClient:
        """ Cliente que retorna sucesso e registra chamdas """
        def __init__(self, *a, **k) -> None:
            self.headers = k.get("headers", {})
            self.cookies: dict = {}

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            pass

        async def get(self, url: str, params: dict | None = None) -> DummyResponse:
            data = {"name": "Produto", "price": 123456}
            if "api/v4/item/get" in url:
                return DummyResponse(200, {"data": data})
            self.cookies["csrftoken"] = "abc"
            return DummyResponse(200)

    monkeypatch.setattr("market_scraper.strategies.json_endpoint.cache_manager", cache)
    monkeypatch.setattr(httpx, "AsyncClient", DummyClient)
    monkeypatch.setattr("market_scraper.strategies.json_endpoint.DataQualityValidator.validate", fake_validate)

    resultado1 = await strategy.get_data("https://shopee.com.br/produto-i.1.2")

    class FailClient:
        """ Cliente que lança erro caso seja utilizado """
        def __init__(self, *a, **k) -> None:
            raise AssertionError("Não deveria executar nova requisição")

    monkeypatch.setattr(httpx, "AsyncClient", FailClient)

    resultado2 = await strategy.get_data("https://shopee.com.br/produto-i.1.2")

    assert resultado1 == resultado2
