""" Testes para a função ``extract_structured_data`` """

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
    