""" Testes unitários para a estratégia ShopeeJsonStrategy baseada em JSON """

import pytest
import httpx

from market_scraper.strategies.json_endpoint import ShopeeJsonStrategy


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
