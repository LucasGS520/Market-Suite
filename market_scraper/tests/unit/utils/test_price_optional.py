from decimal import Decimal
import pytest
from market_scraper.utils.price import parse_optional_price_str


@pytest.mark.parametrize("raw", ["", " ", None])
def test_parse_optional_price_none(raw):
    #Chamada deve resultar retorno nulo
    assert parse_optional_price_str(raw, "http://exemplo.com") is None

def test_parse_optional_price_valid():
    #Deve converter o preço para Decimal corretamente
    valor = parse_optional_price_str("R$ 1.234,56", "http://exemplo.com")
    assert valor == Decimal("1234.56")
    