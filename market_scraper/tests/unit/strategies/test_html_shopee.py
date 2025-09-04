""" Testes específicos para a estratégia ShopeeHtmlStaticStrategy """

import pytest
import httpx

from market_scraper.strategies.html_static import ShopeeHtmlStaticStrategy


@pytest.fixture
def strategy() -> ShopeeHtmlStaticStrategy:
    """ Instância da estratégia da Shopee para uso nos testes """
    return ShopeeHtmlStaticStrategy()

@pytest.fixture
def html_com_next_data() -> str:
    """ HTML fictício contendo ``<script id=\"__NEXT_DATA__\">`` com nome e preço """
    return (
        "<html><head>"
        '<script id="__NEXT_DATA__">'
        '{"props":{"pageProps":{"product":{"name":"Produto Script","price":"10.00","currency":"BRL"}}}}'
        "</script>"
        "</head></html>"
    )

@pytest.fixture
def html_com_meta_tags() -> str:
    """ HTML contendo apenas meta tags de título e preço """
    return (
        "<html><head>"
        '<meta property="og:title" content="Produto Meta" />'
        '<meta itemprop="price" content="20.00" />'
        '<meta itemprop="priceCurrency" content="BRL" />'
        "</head></html>"
    )

@pytest.mark.asyncio
async def test_extrai_dados_de_next_data(strategy: ShopeeHtmlStaticStrategy, html_com_next_data: str, monkeypatch: pytest.MonkeyPatch) -> None:
    """ Verifica extração de nome e preço a partir do script ``__NEXT_DATA__`` """
    async def fake_fetch(self, url: str) -> str:
        #Simula o download do HTML retornando o conteúdo de teste
        return html_com_next_data

    monkeypatch.setattr(ShopeeHtmlStaticStrategy, "_fetch_html", fake_fetch)
    resultado = await strategy.get_data("http://exemplo.com/produto")
    detalhes = resultado["details"]
    assert resultado["status"] == "success"
    assert detalhes["name"] == "Produto Script"
    assert detalhes["current_price"] == "R$ 10,00"

@pytest.mark.asyncio
async def test_fallback_para_meta_tags(strategy: ShopeeHtmlStaticStrategy, html_com_meta_tags: str, monkeypatch: pytest.MonkeyPatch) -> None:
    """ Garante extração correta quando apenas meta tags estão disponíveis """
    async def fake_fetch(self, url: str) -> str:
        #Retorna HTML sem ``__NEXT_DATA__`` para acionar o fallback de meta tags
        return html_com_meta_tags

    monkeypatch.setattr(ShopeeHtmlStaticStrategy, "_fetch_html", fake_fetch)
    resultado = await strategy.get_data("http://exemplo.com/produto")
    detalhes = resultado["details"]
    assert resultado["status"] == "success"
    assert detalhes["name"] == "Produto Meta"
    assert detalhes["current_price"] == "R$ 20,00"

@pytest.mark.asyncio
async def test_normaliza_preco_inteiro(strategy: ShopeeHtmlStaticStrategy, monkeypatch: pytest.MonkeyPatch) -> None:
    """ Garante a conversão correta quando o preço é fornecido como inteiro """
    html = (
        "<html><head>"
        '<script id="__NEXT_DATA__">'
        '{"props":{"pageProps":{"product":{"name":"Produto Int","price":123456,"currency":"BRL"}}}}'
        "</script>"
        "</head></html>"
    )

    async def fake_fetch(self, url: str) -> str:
        return html

    monkeypatch.setattr(ShopeeHtmlStaticStrategy, "_fetch_html", fake_fetch)
    resultado = await strategy.get_data("http://exemplo.com/produto")
    detalhes = resultado["details"]
    assert resultado["status"] == "success"
    assert detalhes["current_price"] == "R$ 1,23"

@pytest.mark.asyncio
@pytest.mark.parametrize("campo", ["price_min", "price_before_discount", "price_min_before_discount"])
async def test_busca_preco_em_campos_alternativos(strategy: ShopeeHtmlStaticStrategy, campo: str, monkeypatch: pytest.MonkeyPatch) -> None:
    """ Verifica extração de preço em diferentes chaves alternativas """
    html = (
        "<html><head>"
        '<script id="__NEXT_DATA__">'
        '{"props":{"pageProps":{"product":{"name":"Produto Alt","currency":"BRL","%s":123456}}}}'
        "</script>"
        "</head></html>"
    ) % campo

    async def fake_fetch(self, url: str) -> str:
        return html

    monkeypatch.setattr(ShopeeHtmlStaticStrategy, "_fetch_html", fake_fetch)
    resultado = await strategy.get_data("http://exemplo.com/produto")
    detalhes = resultado["details"]
    assert resultado["status"] == "success"
    assert detalhes["current_price"] == "R$ 1,23"

@pytest.mark.asyncio
async def test_envia_user_agent(strategy: ShopeeHtmlStaticStrategy, monkeypatch: pytest.MonkeyPatch) -> None:
    """ Verifica se o cabeçalho ``User-Agent`` é enviado na requisição HTTP """

    capturado: dict = {}

    class DummyResponse:
        """ Simula resposta de sucesso do ``httpx`` """
        text = ""
        headers: dict = {}

        def raise_for_status(self) -> None:
            pass

    class DummyAsyncClient:
        """ Cliente assíncrono fictício que registra os cabeçalhos enviados """
        def __init__(self, headers=None, cookies=None, timeout=None, **kwargs):
            capturado.update(headers or {})

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            pass

        async def get(self, url: str) -> DummyResponse:
            return DummyResponse()

    #Substitui o cliente real pelo fictício para inspecionar os cabeçalhos
    monkeypatch.setattr(httpx, "AsyncClient", DummyAsyncClient)

    await strategy._fetch_html("http://exemplo.com/produto")
    assert "User-Agent" in capturado
