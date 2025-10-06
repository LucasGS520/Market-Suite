from decimal import Decimal

from shared.metrics.metrics_scraper import SCRAPER_STEP_INVALID_TOTAL

from market_scraper.utils.validator import DataQualityValidator


def _metric_value(step: str, source: str) -> Decimal:
    sample = SCRAPER_STEP_INVALID_TOTAL.labels(step, source)
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

def test_validator_records_invalid_price() -> None:
    validator = DataQualityValidator()
    before = _metric_value("html_metadata_parser", "exemplo.com")
    result = validator.validate(
        step_name="html_metadata_parser",
        payload={"name": "Produto", "current_price": "abc", "url": ""},
        url="https://exemplo.com/produto",
        source="exemplo.com",
    )
    after = _metric_value("html_metadata_parser", "exemplo.com")
    assert result is None
    assert after == before + Decimal(1)
    