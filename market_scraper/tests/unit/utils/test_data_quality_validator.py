from app.utils.data_quality_validator import DataQualityValidator
import pytest

VALID_DATA = {
    "name": "Produto",
    "url": "https://exemplo.com/p/1",
    "current_price": "R$ 10,00",
    "old_price": "R$ 12,00",
    "shipping": "Frete Grátis",
    "seller": "Loja X",
    "thumbnail": "https://img/1.jpg"
}

def test_validate_accepts_valid_data():
    DataQualityValidator().validate(VALID_DATA)

def test_missing_field_raises_value_error():
    data = VALID_DATA.copy()
    data.pop("name")
    with pytest.raises(ValueError):
        DataQualityValidator().validate(data)

def test_invalid_price_raises_value_error():
    data = VALID_DATA.copy()
    data["current_price"] = "R$ -5,00"
    with pytest.raises(ValueError):
        DataQualityValidator().validate(data)

@pytest.mark.parametrize("shipping", [
    "Frete Grátis",
    "frete gratis",
    "entrega grátis",
    "entrega gratis",
    "Frete pago"
])
def test_validate_accepts_shipping_variations(shipping):
    data = VALID_DATA.copy()
    data["shipping"] = shipping
    DataQualityValidator().validate(data)

def test_implausible_shipping():
    data = VALID_DATA.copy()
    data["shipping"] = "xyz"
    with pytest.raises(ValueError):
        DataQualityValidator().validate(data)

def test_implausible_seller():
    data = VALID_DATA.copy()
    data["seller"] = "1"
    with pytest.raises(ValueError):
        DataQualityValidator().validate(data)
