""" Teste para o ``DataQualityValidator`` """
import pytest

from market_scraper.utils.data_quality_validator import DataQualityValidator

VALID_DATA = {
    "name": "Produto",
    "current_price": "R$ 10,00",
}

def test_validate_accepts_valid_data():
    """ Garantir que dados mínimos válidos sejam aceitos """
    DataQualityValidator().validate(VALID_DATA)

def test_missing_name_raises_value_error():
    data = VALID_DATA.copy()
    data.pop("name")
    with pytest.raises(ValueError):
        DataQualityValidator().validate(data)

def test_missing_price_raises_value_error():
    data = VALID_DATA.copy()
    data.pop("current_price")
    with pytest.raises(ValueError):
        DataQualityValidator().validate(data)


def test_invalid_price_raises_value_error():
    data = VALID_DATA.copy()
    data["current_price"] = "R$ -5,00"
    with pytest.raises(ValueError):
        DataQualityValidator().validate(data)

def test_extra_fields_are_ignored():
    data = VALID_DATA.copy()
    data["seller"] = "1"
    data.update({"seller": "Loja X", "url": "https://exemplo.com/p/1"})
    DataQualityValidator().validate(data)
