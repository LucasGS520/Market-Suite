""" Testes para o validator de qualidade dos parsers """

from decimal import Decimal
import sys
from types import ModuleType

from shared.metrics.metrics_scraper import (
    SCRAPER_STEP_INVALID_TOTAL,
    SCRAPER_VALIDATION_REJECT_TOTAL,
)
from structlog.testing import capture_logs

if "price_parser" not in sys.modules:
    dummy_module = ModuleType("price_parser")

    class _DummyPrice:
        """ Implementação mínima para permitir importação do módulo real """
        def __init__(self, amount: Decimal | None = None) -> None:
            self.amount = amount

        @classmethod
        def fromstring(cls, raw: str) -> "_DummyPrice":
            return cls(amount=None)
        
    dummy_module.Price = _DummyPrice
    sys.modules["price_parser"] = dummy_module

from market_scraper.utils.validator import DataQualityValidator


def _metric_value(step: str, domain: str, result: str) -> Decimal:
    sample = SCRAPER_STEP_INVALID_TOTAL.labels(step, domain, result)
    return Decimal(sample._value.get())

def _reject_metric_value(domain: str, step: str, reason: str) -> Decimal:
    sample = SCRAPER_VALIDATION_REJECT_TOTAL.labels(domain, step, reason)
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
    assert result.is_valid
    assert result.payload == {
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
    assert result.is_valid
    assert result.payload == {
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
    assert result.is_valid
    assert result.payload == {
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
    assert result.is_valid
    assert result.payload == {
        "name": "Produto",
        "current_price": "200.00",
        "url": "https://outro.com/item",
        "source": "loja.teste.com",
    }

def test_validator_records_invalid_price() -> None:
    validator = DataQualityValidator()
    before = _metric_value("html_metadata_parser", "exemplo.com", "price_invalid")
    before_reject = _reject_metric_value("exemplo.com", "html_metadata_parser", "price_invalid")
    result = validator.validate(
        step_name="html_metadata_parser",
        payload={"name": "Produto", "current_price": "abc", "url": ""},
        url="https://exemplo.com/produto",
        source="exemplo.com",
    )
    after = _metric_value("html_metadata_parser", "exemplo.com", "price_invalid")
    after_reject = _reject_metric_value("exemplo.com", "html_metadata_parser", "price_invalid")
    assert not result.is_valid
    assert result.reason_code == "price_invalid"
    assert after == before + Decimal(1)
    assert after_reject == before_reject + Decimal(1)

def test_validator_records_domain_from_full_source() -> None:
    validator = DataQualityValidator()
    before = _metric_value("html_metadata_parser", "loja.teste.com", "price_invalid")
    before_reject = _reject_metric_value("loja.teste.com", "html_metadata_parser", "price_invalid")
    result = validator.validate(
        step_name="html_metadata_parser",
        payload={"name": "Produto", "current_price": "abc", "url": ""},
        url="https://exemplo.com/produto",
        source="https://loja.teste.com/oferta",
    )
    after = _metric_value("html_metadata_parser", "loja.teste.com", "price_invalid")
    assert not result.is_valid
    assert after == before + Decimal(1)
    after_reject = _reject_metric_value("loja.teste.com", "html_metadata_parser", "price_invalid")
    assert after_reject == before_reject + Decimal(1)

def test_validator_accepts_approximate_price_with_tolerance() -> None:
    validator = DataQualityValidator(price_tolerance=Decimal("0.25"))
    payload = {
        "name": "Produto",
        "current_price": "R$ 100,00 - R$ 110,00",
        "url": "https://exemplo.com/produto",
    }
    result = validator.validate(
        step_name="json_ld_parser",
        payload=payload,
        url="https://exemplo.com/produto",
        source="exemplo.com",
    )
    assert result.is_valid
    assert result.payload is not None
    assert result.payload["current_price"] == "100.00"

def test_validator_logs_reason_code() -> None:
    """ Confere que o validador registre logs estruturados com o motivo """
    validator = DataQualityValidator()
    payload = {"name": "Produto", "current_price": "abc", "url": ""}

    with capture_logs() as captured:
        result = validator.validate(
            step_name="html_metadata_parser",
            payload=payload,
            url="https://exemplo.com/produto",
            source="exemplo.com",
            parser_name="html_metadata_parser",
            dump_path="/tmp/dump.html",
        )

    assert not result.is_valid
    log_entry = next(
        (entry for entry in captured if entry["event"] == "validation_rejected_payload"),
        None,
    )
    assert log_entry is not None
    assert log_entry["reason_code"] == "price_invalid"
    assert log_entry["parser_name"] == "html_metadata_parser"
    assert log_entry["dump_path"] == "/tmp/dump.html"
    