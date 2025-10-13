""" Testes para o validator de dados do scraper """

from decimal import Decimal

from shared.metrics.metrics_scraper import SCRAPER_STEP_INVALID_TOTAL

from market_scraper.utils.validator import DataQualityValidator


def _metric_value(step: str, domain: str, result: str) -> Decimal:
    sample = SCRAPER_STEP_INVALID_TOTAL.labels(step, domain, result)
    return Decimal(sample._value.get())

def test_validator_normalizes_payload() -> None:
    validator = DataQualityValidator()
    payload = {
        "name": " Produto ",
        "current_price": "R$ 10,00",
        "url": "https://exemplo.com/produto",
        "source": "",
    }
    result = validator.validate(
        step_name="json_ld_parser",
        payload=payload,
        url="https://exemplo.com/produto",
        source="exemplo.com",
    )
    assert result == {
        "name": "Produto",
        "current_price": "10.00",
        "url": "https://exemplo.com/produto",
        "source": "exemplo.com",
    }

def test_validator_replaces_non_domain_source() -> None:
    validator = DataQualityValidator()
    payload = {
        "name": "Produto",
        "current_price": "100",
        "url": "",
        "source": "structured_data",
    }
    result = validator.validate(
        step_name="json_ld_parser",
        payload=payload,
        url="https://exemplo.com/produto",
        source="exemplo.com",
    )
    assert result == {
        "name": "Produto",
        "current_price": "100.00",
        "url": "https://exemplo.com/produto",
        "source": "exemplo.com",
    }

def test_validator_uses_fallback_when_source_missing() -> None:
    """ Garante que payloads sem origem utilizem o fallback informado """
    validator = DataQualityValidator()
    payload = {
        "name": "Produto",
        "current_price": "99.99",
        "url": "https://exemplo.com/produto",
    }
    result = validator.validate(
        step_name="json_ld_parser",
        payload=payload,
        url="https://exemplo.com/produto",
        source="exemplo.com",
    )
    assert result == {
        "name": "Produto",
        "current_price": "99.99",
        "url": "https://exemplo.com/produto",
        "source": "exemplo.com",
    }

def test_validator_uses_hostname_from_source_url() -> None:
    validator = DataQualityValidator()
    payload = {
        "name": "Produto",
        "current_price": "200",
        "url": "https://outro.com/item",
        "source": "https://loja.teste.com/item",
    }
    result = validator.validate(
        step_name="json_ld_parser",
        payload=payload,
        url="https://exemplo.com/produto",
        source="exemplo.com",
    )
    assert result == {
        "name": "Produto",
        "current_price": "200.00",
        "url": "https://outro.com/item",
        "source": "loja.teste.com",
    }

def test_validator_records_invalid_price() -> None:
    validator = DataQualityValidator()
    before = _metric_value("html_metadata_parser", "exemplo.com", "price_invalid")
    result = validator.validate(
        step_name="html_metadata_parser",
        payload={"name": "Produto", "current_price": "abc", "url": ""},
        url="https://exemplo.com/produto",
        source="exemplo.com",
    )
    after = _metric_value("html_metadata_parser", "exemplo.com", "price_invalid")
    assert result is None
    assert after == before + Decimal(1)
