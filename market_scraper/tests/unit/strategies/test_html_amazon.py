""" Testes para extratores específicos da Amazon """

import pytest

from market_scraper.strategies.html_static import AmazonHtmlStaticStrategy


@pytest.fixture
def strategy() -> AmazonHtmlStaticStrategy:
    """ Instância da estratégia da Amazon para os testes """
    return AmazonHtmlStaticStrategy()

@pytest.fixture
def html_com_jsonld() -> str:
    """ HTML fictício com bloco JSON-LD de produto """
    return (
        "<html><head>"
        '<script type="application/ld+json">'
        '{"@context":"https://schema.org","@type":"Product","name":"Produto JSON-LD Amazon","offers":{"@type":"Offer","price":"99.90","priceCurrency":"BRL"}}'
        "</script>"
        "</head></html>"
    )

@pytest.fixture
def html_meta_tags() -> str:
    """ HTML contendo apenas meta tags com dados de produto """
    return (
        "<html><head>"
        '<meta property="og:title" content="Produto Meta Amazon" />'
        '<meta property="og:price:amount" content="89.99" />'
        '<meta property="og:price:currency" content="USD" />'
        '<meta property="product:price:amount" content="89.99" />'
        '<meta property="product:price:currency" content="USD" />'
        "</head></html>"
    )

@pytest.fixture
def html_fallback() -> str:
    """ HTML com elementos de fallback para título e preço """
    return (
        "<html><body>"
        '<span id="productTitle">Produto Fallback Amazon</span>'
        '<span id="priceblock_ourprice">R$ 1.234,56</span>'
        "</body></html>"
    )

@pytest.mark.asyncio
async def test_extrai_de_json_ld(strategy: AmazonHtmlStaticStrategy, html_com_jsonld: str, monkeypatch: pytest.MonkeyPatch) -> None:
    """ Valida extração de nome e preço a partir de bloco JSON-LD """
    async def fake_fetch(self, url: str) -> str:
        return html_com_jsonld

    monkeypatch.setattr(AmazonHtmlStaticStrategy, "_fetch_html", fake_fetch)
    resultado = await strategy.get_data("http://exemplo.com/produto")
    detalhes = resultado["details"]
    assert resultado["status"] == "success"
    assert detalhes["name"] == "Produto JSON-LD Amazon"
    assert detalhes["current_price"] == "R$ 99,90"

@pytest.mark.asyncio
async def test_extrai_de_json_ld_offers_array(strategy: AmazonHtmlStaticStrategy, monkeypatch: pytest.MonkeyPatch) -> None:
    """ Garante uso de ``offers.offers[0]`` em estruturas ``AggregateOffer`` """
    html = (
        "<html><head>"
        '<script type="application/ld+json">'
        '{"@context":"https://schema.org","@type":"Product","name":"Produto Nested Amazon","offers":{"@type":"AggregateOffer","offers":[{"@type":"Offer","price":"77.88","priceCurrency":"BRL"}]}}'
        "</script>"
        "</head></html>"
    )

    async def fake_fetch(self, url: str) -> str:
        return html

    monkeypatch.setattr(AmazonHtmlStaticStrategy, "_fetch_html", fake_fetch)
    resultado = await strategy.get_data("http://exemplo.com/produto")
    detalhes = resultado["details"]
    assert resultado["status"] == "success"
    assert detalhes["name"] == "Produto Nested Amazon"
    assert detalhes["current_price"] == "R$ 77,88"

@pytest.mark.asyncio
async def test_extrai_de_json_ld_lowprice(strategy: AmazonHtmlStaticStrategy, monkeypatch: pytest.MonkeyPatch) -> None:
    """ Utiliza ``lowPrice`` quando ``price`` está ausente """
    html = (
        "<html><head>"
        '<script type="application/ld+json">'
        '{"@context":"https://schema.org","@type":"Product","name":"Produto Low Amazon","offers":{"@type":"AggregateOffer","lowPrice":"55.66","priceCurrency":"USD"}}'
        "</script>"
        "</head></html>"
    )

    async def fake_fetch(self, url: str) -> str:
        return html

    monkeypatch.setattr(AmazonHtmlStaticStrategy, "_fetch_html", fake_fetch)
    resultado = await strategy.get_data("http://exemplo.com/produto")
    detalhes = resultado["details"]
    assert resultado["status"] == "success"
    assert detalhes["name"] == "Produto Low Amazon"
    assert detalhes["current_price"] == "USD 55,66"

@pytest.mark.asyncio
async def test_extrai_de_meta_tags(strategy: AmazonHtmlStaticStrategy, html_meta_tags: str, monkeypatch: pytest.MonkeyPatch) -> None:
    """ Garante extração correta quando apenas meta tags estão presentes """
    async def fake_fetch(self, url: str) -> str:
        return html_meta_tags

    monkeypatch.setattr(AmazonHtmlStaticStrategy, "_fetch_html", fake_fetch)
    resultado = await strategy.get_data("http://exemplo.com/produto")
    detalhes = resultado["details"]
    assert resultado["status"] == "success"
    assert detalhes["name"] == "Produto Meta Amazon"
    assert detalhes["current_price"] == "USD 89,99"

@pytest.mark.asyncio
async def test_extrai_de_fallback(strategy: AmazonHtmlStaticStrategy, html_fallback: str, monkeypatch: pytest.MonkeyPatch) -> None:
    """ verifica uso dos seletores de fallback da Amazon """
    async def fake_fetch(self, url: str) -> str:
        return html_fallback

    monkeypatch.setattr(AmazonHtmlStaticStrategy, "_fetch_html", fake_fetch)
    resultado = await strategy.get_data("http://exemplo.com/produto")
    detalhes = resultado["details"]
    assert resultado["status"] == "success"
    assert detalhes["name"] == "Produto Fallback Amazon"
    assert detalhes["current_price"] == "R$ 1.234,56"

@pytest.mark.asyncio
async def test_extrai_de_saleprice(strategy: AmazonHtmlStaticStrategy, monkeypatch: pytest.MonkeyPatch) -> None:
    """ Garante extração a partir de ``#priceblock_saleprice`` """
    html = (
        "<html><body>"
        '<span id="productTitle">Produto Sale Amazon</span>'
        '<span id="priceblock_saleprice">R$ 2.345,67</span>'
        "</body></html>"
    )

    async def fake_fetch(self, url: str) -> str:
        return html

    monkeypatch.setattr(AmazonHtmlStaticStrategy, "_fetch_html", fake_fetch)
    resultado = await strategy.get_data("http://exemplo.com/produto")
    detalhes = resultado["details"]
    assert resultado["status"] == "success"
    assert detalhes["current_price"] == "R$ 2.345,67"

@pytest.mark.asyncio
async def test_extrai_de_price_inside_buybox(strategy: AmazonHtmlStaticStrategy, monkeypatch: pytest.MonkeyPatch) -> None:
    """ Verifica extração a partir de ``#price_inside_buybox`` """

    html = (
        "<html><body>"
        '<span id="productTitle">Produto BuyBox Amazon</span>'
        '<span id="price_inside_buybox">R$ 3.456,78</span>'
        "</body></html>"
    )

    async def fake_fetch(self, url: str) -> str:
        return html

    monkeypatch.setattr(AmazonHtmlStaticStrategy, "_fetch_html", fake_fetch)
    resultado = await strategy.get_data("http://exemplo.com/produto")
    detalhes = resultado["details"]
    assert resultado["status"] == "success"
    assert detalhes["name"] == "Produto BuyBox Amazon"
    assert detalhes["current_price"] == "R$ 3.456,78"

@pytest.mark.asyncio
async def test_extrai_de_whole_fraction(strategy: AmazonHtmlStaticStrategy, monkeypatch: pytest.MonkeyPatch) -> None:
    """ Combina ``span.a-price-whole`` e ``span.a-price-fraction`` para formar o preço """
    html = (
        "<html><body>"
        '<span id="productTitle">Produto Partes Amazon</span>'
        '<span class="a-price-symbol">R$</span>'
        '<span class="a-price-whole">5.678</span>'
        '<span class="a-price-fraction">90</span>'
        "</body></html>"
    )

    async def fake_fetch(self, utl: str) -> str:
        return html

    monkeypatch.setattr(AmazonHtmlStaticStrategy, "_fetch_html", fake_fetch)
    resultado = await strategy.get_data("http://exemplo.com/produto")
    detalhes = resultado["details"]
    assert resultado["status"] == "success"
    assert detalhes["name"] == "Produto Partes Amazon"
    assert detalhes["current_price"] == "R$ 5.678,90"

@pytest.mark.asyncio
async def test_prioriza_core_price_display(strategy: AmazonHtmlStaticStrategy, monkeypatch: pytest.MonkeyPatch) -> None:
    """ Seleciona o preço correto quando há mútiplos ``span.a-offscreen`` """
    html = (
        "<html><body>"
        '<span id="productTitle">Produto CorePrice</span>'
        '<div id="corePriceDisplay_desktop_feature_div">'
        '<span class="a-price"><span class="a-offscreen">R$ 9,99</span></span>'
        '</div>'
        '<div id="outro"><span class="a-offscreen">R$ 100,00</span></div>'
        "</body></html>"
    )

    async def fake_fetch(self, url: str) -> str:
        return html

    monkeypatch.setattr(AmazonHtmlStaticStrategy, "_fetch_html", fake_fetch)
    resultado = await strategy.get_data("http://exemplo.com/produto")
    detalhes = resultado["details"]
    assert resultado["status"] == "success"
    assert detalhes["current_price"] == "R$ 9,99"

@pytest.mark.asyncio
async def test_extrai_de_title(strategy: AmazonHtmlStaticStrategy, monkeypatch: pytest.MonkeyPatch) -> None:
    """ Utiliza ``#title`` quando ``#productTitle`` não está presente """
    html = (
        "<html><head>"
        '<meta property="og:title" content="Produto Meta" />'
        "</head><body>"
        '<span id="Title">Produto Pelo Title</span>'
        '<span id="priceblock_ourprice">R$ 1.111,00</span>'
        "</body></html>"
    )

    async def fake_fetch(self, url: str) -> str:
        return html

    monkeypatch.setattr(AmazonHtmlStaticStrategy, "_fetch_html", fake_fetch)
    resultado = await strategy.get_data("http://exemplo.com/produto")
    detalhes = resultado["details"]
    assert resultado["status"] == "success"
    assert detalhes["name"] == "Produto Pelo Title"
    assert detalhes["current_price"] == "R$ 1.111,00"

@pytest.mark.asyncio
async def test_prioriza_producttitle_variado(strategy: AmazonHtmlStaticStrategy, monkeypatch: pytest.MonkeyPatch) -> None:
    """ Prioriza ids que contenham ``productTitle`` sobre ``#title`` e meta tags """
    html = (
        "<html><head>"
        '<meta property="og:title" content="Produto Meta" />'
        "</head><body>"
        '<span id="PRODUCTTITLE123">Produto Variado</span>'
        '<span id="title">Outro Produto</span>'
        '<span id="priceblock_ourprice">R$ 2.222,00</span>'
        "</body></html>"
    )

    async def fake_fetch(self, url: str) -> str:
        return html

    monkeypatch.setattr(AmazonHtmlStaticStrategy, "_fetch_html", fake_fetch)
    resultado = await strategy.get_data("http://exemplo.com/produto")
    detalhes = resultado["details"]
    assert resultado["status"] == "success"
    assert detalhes["name"] == "Produto Variado"
    assert detalhes["current_price"] == "R$ 2.222,00"
