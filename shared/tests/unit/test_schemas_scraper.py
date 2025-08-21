""" Testes para o esquema de scraping com suporte a Decimal """

from decimal import Decimal

from shared.schemas.schemas_scraper import ScraperResponse

def test_precisao_dos_precos() -> None:
    dados = ScraperResponse(current_price="0.10", old_price="0.20")
    assert isinstance(dados.current_price, Decimal)
    assert isinstance(dados.old_price, Decimal)
    assert dados.current_price + dados.old_price == Decimal("0.30")
