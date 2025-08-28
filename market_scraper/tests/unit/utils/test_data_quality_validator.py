""" Teste para o ``DataQualityValidator`` """
import pytest

from market_scraper.utils.data_quality_validator import DataQualityValidator

VALID_DATA = {
    "name": "Produto",
    "current_price": "R$ 10,00",
}

@pytest.mark.parametrize(
    "price",
    ["R$ 10,00", "US$ 10.00", "€ 10,00"],
)
def test_validate_accepts_valid_data(price):
    """ Garantir que dados mínimos válidos sejam aceitos em múltiplas moedas """
    data = {"name": "Produto", "current_price": price}
    DataQualityValidator().validate(data)

def test_missing_name_raises_value_error():
    """ Verificar que ausência do campo ``name`` gera erro """
    data = VALID_DATA.copy()
    data.pop("name")
    with pytest.raises(ValueError):
        DataQualityValidator().validate(data)

def test_missing_price_raises_value_error():
    """ verificar que ausência do campo ``current_price`` gera erro """
    data = VALID_DATA.copy()
    data.pop("current_price")
    with pytest.raises(ValueError):
        DataQualityValidator().validate(data)


@pytest.mark.parametrize(
    "price",
    ["R$ -5,00", "US$ -5.00", "€ -5,00"],
)
def test_invalid_price_raises_value_error(price):
    """ Certificar que preços negativos sejam rejeitados independentemente da moeda """
    data = VALID_DATA.copy()
    data["current_price"] = price
    with pytest.raises(ValueError):
        DataQualityValidator().validate(data)

def test_extra_fields_are_ignored():
    """ Garantir que campos adicionais não gerem erro """
    data = VALID_DATA.copy()
    data["seller"] = "1"
    data.update({"seller": "Loja X", "url": "https://exemplo.com/p/1"})
    DataQualityValidator().validate(data)
