""" Testes unitários para a estratégia de HTML estático """

import logging

import pytest
import httpx

from market_scraper.strategies.html_static import HtmlStaticStrategy


@pytest.fixture
def strategy() -> HtmlStaticStrategy:
    """ Instância padrão de estratégia para uso nos testes """
    return HtmlStaticStrategy()


@pytest.fixture
def html_json_ld() -> str:
    """ HTML mínimo contendo bloco JSON-LD de produto """
    return (
        "<html><head>"
        '<script type="application/ld+json">'
        '{"@type":"Product","name":"Produto JSON","offers":{"price":"10.00","priceCurrency":"BRL"}}'
        "</script>" "</head></html>"
    )

@pytest.fixture
def html_meta_tags() -> str:
    """ HTML mínimo com meta tags de preço e título """
    return (
        "<html><head>"
        '<meta property="og:title" content="Produto Meta" />'
        '<meta itemprop="price" content="20.00" />'
        '<meta itemprop="priceCurrency" content="BRL" />'
        "</head></html>"
    )

@pytest.fixture
def html_og_meta_tags() -> str:
    """ HTML contendo apenas meta tags ``og:price:*`` """
    return (
        "<html><head>"
        '<meta property="og:title" content="Produto OG" />'
        '<meta property="og:price:amount" content="25.00" />'
        '<meta property="og:price:currency" content="USD" />'
        "</head></html>"
    )

@pytest.fixture
def html_json_ld_price_spec() -> str:
    """ HTML com JSON-LD onde a moeda está em ``priceSpecification`` """
    return (
        "<html><head>"
        '<script type="application/ld+json">'
        '{"@type":"Product","name":"Produto PriceSpec","offers":{"priceSpecification":{"price":"30.00","priceCurrency":"USD"}}}'
        "</script>" "</head></html>"
    )

@pytest.fixture
def html_json_ld_offers_list() -> str:
    """ HTML com JSON-LD em que ``offers`` contém uma lista interna """
    return (
        "<html><head>"
        '<script type="application/ld+json">'
        '{"@type":"Product","name":"Produto Lista","offers":{"@type":"AggregateOffer","offers":[{"price":"15.00","priceCurrency":"BRL"}]}}'
        "</script>" "</head></html>"
    )

@pytest.fixture
def html_json_ld_low_price() -> str:
    """ HTML com JSON-LD usando ``lowPrice`` sem ``price`` """
    return (
        "<html><head>"
        '<script type="application/ld+json">'
        '{"@type":"Product","name":"Produto Low","offers":{"lowPrice":"40.00","priceCurrency":"BRL"}}'
        "</script>" "</head></html>"
    )

@pytest.fixture
def html_invalido() -> str:
    """ HTML sem informações necessárias para validação """
    return "<html><head><title>Vazio</title></head></html>"

@pytest.mark.asyncio
async def test_extrai_dados_de_json_ld(strategy: HtmlStaticStrategy, html_json_ld: str, monkeypatch: pytest.MonkeyPatch) -> None:
    """ Verifica extração de dados quando há JSON-LD válido """
    async def fake_fetch(self, url: str) -> str:
        return html_json_ld

    #Ignora validações rígidas para focar apenas na extração
    monkeypatch.setattr("market_scraper.strategies.html_static.DataQualityValidator.validate", lambda self, data: None)
    monkeypatch.setattr(HtmlStaticStrategy, "_fetch_html", fake_fetch)
    resultado = await strategy.get_data("http://exemplo.com/produto")
    detalhes = resultado["details"]
    assert resultado["status"] == "success"
    assert detalhes["name"] == "Produto JSON"
    assert detalhes["current_price"] == "R$ 10,00"

@pytest.mark.asyncio
async def test_extrai_dados_de_meta_tags(strategy: HtmlStaticStrategy, html_meta_tags: str, monkeypatch: pytest.MonkeyPatch) -> None:
    """ Verifica extração de dados quando apenas meta tags estão presentes """
    async def fake_fetch(self, url: str) -> str:
        return html_meta_tags

    #Ignora validações rígidas para focar apenas na extração
    monkeypatch.setattr("market_scraper.strategies.html_static.DataQualityValidator.validate", lambda self, data: None)
    monkeypatch.setattr(HtmlStaticStrategy, "_fetch_html", fake_fetch)
    resultado = await strategy.get_data("http://exemplo.com/produto")
    detalhes = resultado["details"]
    assert resultado["status"] == "success"
    assert detalhes["name"] == "Produto Meta"
    assert detalhes["current_price"] == "R$ 20,00"

@pytest.mark.asyncio
async def test_extrai_de_meta_tags_og(strategy: HtmlStaticStrategy, html_og_meta_tags: str, monkeypatch: pytest.MonkeyPatch) -> None:
    """ Garante extração quando apenas tags ``og:price:*`` estão disponíveis """
    async def fake_fetch(self, url: str) -> str:
        return html_og_meta_tags

    #Ignora validações rígidas para focar apenas na extração
    monkeypatch.setattr("market_scraper.strategies.html_static.DataQualityValidator.validate", lambda self, data: None)
    monkeypatch.setattr(HtmlStaticStrategy, "_fetch_html", fake_fetch)
    resultado = await strategy.get_data("http://exemplo.com/produto")
    detalhes = resultado["details"]
    assert resultado["status"] == "success"
    assert detalhes["name"] == "Produto OG"
    assert detalhes["current_price"] == "USD 25,00"

@pytest.mark.asyncio
async def test_extrai_moeda_de_price_specification(strategy: HtmlStaticStrategy, html_json_ld_price_spec: str, monkeypatch: pytest.MonkeyPatch) -> None:
    """ Verifica extração da moeda dentro de ``priceSpecification`` """
    async def fake_fetch(self, url: str) -> str:
        return html_json_ld_price_spec

    #Ignora validação para testar apenas a extração
    monkeypatch.setattr("market_scraper.strategies.html_static.DataQualityValidator.validate", lambda self, data: None)
    monkeypatch.setattr(HtmlStaticStrategy, "_fetch_html", fake_fetch)
    resultado = await strategy.get_data("http://exemplo.com/produto")
    detalhes = resultado["details"]
    assert resultado["status"] == "success"
    assert detalhes["name"] == "Produto PriceSpec"
    assert detalhes["current_price"] == "USD 30,00"

@pytest.mark.asyncio
async def test_extrai_de_ofertas_agrupadas(strategy: HtmlStaticStrategy, html_json_ld_offers_list: str, monkeypatch: pytest.MonkeyPatch) -> None:
    """ Garante extração quando ``offers`` possui lista interna """
    async def fake_fetch(self, url: str) -> str:
        return html_json_ld_offers_list

    monkeypatch.setattr("market_scraper.strategies.html_static.DataQualityValidator.validate", lambda self, data: None)
    monkeypatch.setattr(HtmlStaticStrategy, "_fetch_html", fake_fetch)
    resultado = await strategy.get_data("http://exemplo.com/produto")
    detalhes = resultado["details"]
    assert resultado["status"] == "success"
    assert detalhes["name"] == "Produto Lista"
    assert detalhes["current_price"] == "R$ 15,00"

@pytest.mark.asyncio
async def test_extrai_low_price_quando_price_ausente(strategy: HtmlStaticStrategy, html_json_ld_low_price: str, monkeypatch: pytest.MonkeyPatch) -> None:
    """ Utiliza ``lowPrice`` como preço quando ``price`` não existe """
    async def fake_fetch(self, url: str) -> str:
        return html_json_ld_low_price

    monkeypatch.setattr("market_scraper.strategies.html_static.DataQualityValidator.validate", lambda self, data: None)
    monkeypatch.setattr(HtmlStaticStrategy, "_fetch_html", fake_fetch)
    resultado = await strategy.get_data("http://exemplo.com/produto")
    detalhes = resultado["details"]
    assert resultado["status"] == "success"
    assert detalhes["name"] == "Produto Low"
    assert detalhes["current_price"] == "R$ 40,00"

@pytest.mark.asyncio
async def test_retorna_erro_quando_html_invalido(strategy: HtmlStaticStrategy, html_invalido: str, monkeypatch: pytest.MonkeyPatch) -> None:
    """ Garante retorno de erro detalhado quando a validação falha """
    async def fake_fetch(self, url: str) -> str:
        return html_invalido

    #Força o validador a lançar um ``ValueError`` conhecido
    def fake_validate(self, data: dict) -> None:
        raise ValueError("campos obrigatórios ausentes")

    #Captura os parâmetros passados ao logger.warning
    capturado: dict = {}

    def fake_warning(msg, **k):
        capturado.update(k)

    monkeypatch.setattr(HtmlStaticStrategy, "_fetch_html", fake_fetch)
    monkeypatch.setattr("market_scraper.strategies.html_static.DataQualityValidator.validate", fake_validate)
    monkeypatch.setattr("market_scraper.strategies.html_static.logger.warning", fake_warning)

    resultado = await strategy.get_data("http://exemplo.com/produto")
    assert resultado == {"status": "error", "detail": "campos obrigatórios ausentes"}
    #Verifica se a mensagem detalhada foi registrada no logger estruturado
    assert capturado.get("erro") == "campos obrigatórios ausentes"

@pytest.mark.asyncio
async def test_retorna_erro_quando_fetch_falha(strategy: HtmlStaticStrategy, monkeypatch: pytest.MonkeyPatch) -> None:
    """ Retorna erro caso ocorra ``HTTPError`` ao baixar a página """
    async def fake_fetch(self, url: str) -> str:
        raise httpx.HTTPError("falha simulada")

    monkeypatch.setattr(HtmlStaticStrategy, "_fetch_html", fake_fetch)
    resultado = await strategy.get_data("http://exemplo.com/produto")
    assert resultado == {"status": "error"}

@pytest.mark.asyncio
async def test_define_referer_dinamico(monkeypatch: pytest.MonkeyPatch) -> None:
    """ Garante que o cabeçalho `´Referer`` corresponde ao domínio base """
    capturado: dict = {}

    class DummyClient:
        """ Cliente ``httpx`` falso que captura os cabeçalhos enviados """
        def __init__(self, *a, **k):
            capturado.update(k.get("headers", {}))

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            pass

        async def get(self, url: str):
            class Resp:
                text = ""

                def raise_for_status(self) -> None:
                    pass

            return Resp()

    monkeypatch.setattr(httpx, "AsyncClient", DummyClient)
    estrategia = HtmlStaticStrategy()
    await estrategia._fetch_html("https://exemplo.com/produto")
    assert capturado["Referer"] == "https://exemplo.com/"

@pytest.mark.asyncio
async def test_segue_redirecionamento(strategy: HtmlStaticStrategy, monkeypatch: pytest.MonkeyPatch) -> None:
    """ Garante que ``_fetch_html`` segue redirecionamento e retorna o HTML final """
    conteudo_final = "<html><body>ok</body></html>"

    async def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/produto":
            #Simula resposta 302 apontando para a URL final
            return httpx.Response(302, headers={"Location": "http://teste.com/produto-final"})
        if request.url.path == "/produto-final":
            #Retorna o HTML final após seguir o redirecionamento
            return httpx.Response(200, text=conteudo_final)
        return httpx.Response(404)

    transporte = httpx.MockTransport(handler)

    original_async_client = httpx.AsyncClient

    def client_factory(*args, **kwargs):
        kwargs["transport"] = transporte
        return original_async_client(*args, **kwargs)

    monkeypatch.setattr(httpx, "AsyncClient", client_factory)

    html = await strategy._fetch_html("http://teste.com/produto")
    assert html == conteudo_final

@pytest.mark.asyncio
@pytest.mark.parametrize("status", [302, 404])
async def test_log_inclui_location_quando_http_error(strategy: HtmlStaticStrategy, monkeypatch: pytest.MonkeyPatch, caplog, status: int) -> None:
    """ Simula erros HTTP e verifica se o cabeçalho ``Location`` é registrado no log """
    location = f"https://erro.com/{status}"

    async def fake_fetch(self, url: str) -> str:
        request = httpx.Request("GET", url)
        response = httpx.Response(
            status_code=status,
            headers={"Location": location},
            request=request,
            text="x" * 300,
        )
        raise httpx.HTTPStatusError("erro", request=request, response=response)

    monkeypatch.setattr(HtmlStaticStrategy, "_fetch_html", fake_fetch)

    with caplog.at_level(logging.ERROR):
        resultado = await strategy.get_data("http://exemplo.com/produto")

    assert resultado == {"status": "error"}
    assert location in caplog.text
