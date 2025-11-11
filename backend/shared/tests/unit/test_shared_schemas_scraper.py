""" Testes para o esquema de scraping com suporte a tipos nativos """

from decimal import Decimal

from backend.shared.schemas.shared_schemas_scraper import ParserResponse

def test_precisao_dos_precos() -> None:
    dados = ParserResponse(current_price="0.10")
    assert isinstance(dados.current_price, Decimal)
    assert dados.current_price == Decimal("0.10")

def test_campo_marketplace_preenche_source() -> None:
    dados = ParserResponse(current_price="1.00", marketplace="example.com")
    assert dados.source == "example.com"
