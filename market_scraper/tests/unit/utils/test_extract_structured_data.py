""" Testes para a função ``extract_structured_data`` """

import pytest

from market_scraper.utils.extract_structured_data import extract_structured_data


def test_extrai_json_ld_basico() -> None:
    """ Verifica se o JSON-LD é extraido corretamente do HTML """
    html = (
        "<html><head>"
        '<script type="application/ld+json">'
        '{"@context":"https://schema.org","@type":"Product","name":"Produto Extruct","offers":{"price":"10.00","priceCurrency":"BRL"}}'
        "</script>"
        "</head></html>"
    )
    dados = extract_structured_data(html, "https://exemplo.com")
    assert dados["json-ld"][0]["@type"] == "Product"
    assert dados["json-ld"][0]["name"] == "Produto Extruct"
    
def test_fallback_selectolax_recupera_dados(monkeypatch: pytest.MonkeyPatch) -> None:
    """ Garante que o fallback com selectolax devolve estrutura compátivel """
    html = (
        "<html><head>"
        '<script type="application/ld+json">'
        "{\"@context\":\"https://schema.org\",\"@type\":\"Product\",\"name\":\"Produto Fallback\"}"
        "</script>"
        "<meta property=\"og:title\" content=\"Produto OG\" />"
        "</head><body>"
        '<div itemscope itemtype="https://schema.org/Product">'
        '<span itemprop="name">Produto Microdata</span>'
        "</div>"
        "</body></html>"
    )

    def fake_extract(*args, **kwargs): 
        return {"json-ld": [], "microdata": [], "opengraph": []}
    
    monkeypatch.setattr(
        "market_scraper.utils.extract_structured_data.extruct.extract",
        fake_extract,
    )

    dados = extract_structured_data(html, "https://exemplo.com")
    assert dados["json-ld"][0]["name"] == "Produto Fallback"
    assert dados["microdata"][0]["properties"]["name"] == "Produto Microdata"
    assert dados["opengraph"][0]["od:title"] == "Produto OG"
    