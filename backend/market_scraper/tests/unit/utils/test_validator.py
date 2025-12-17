""" Testes para o validator de qualidade dos parsers """

from decimal import Decimal
import sys
from types import ModuleType

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
        "availability": None,
        "last_status": None,
        "currency": None,
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
        "availability": None,
        "last_status": None,
        "currency": None,
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
        "availability": None,
        "last_status": None,
        "currency": None,
    }

def test_validator_normalizes_url_without_scheme() -> None:
    """Confere que a URL resultante usa as mesmas regras do utilitário compartilhado"""
    validator = DataQualityValidator()
    payload = {
        "name": "Produto",
        "current_price": "50",
        "url": "mercadolivre.com.br/MLB-123",
        "source": "mercadolivre.com.br",
    }
    result = validator.validate(
        step_name="json_ld_parser",
        payload=payload,
        url="https://mercadolivre.com.br/MLB-123",
        source="mercadolivre.com.br",
    )

    assert result.is_valid
    assert result.payload is not None
    assert result.payload["url"] == "https://mercadolivre.com.br/MLB-123"

def test_validator_reuses_fallback_when_parser_url_invalid() -> None:
    """Garante resiliência quando o parser gera endereços malformados"""
    validator = DataQualityValidator()
    payload = {
        "name": "Produto",
        "current_price": "50",
        "url": "javascript:alert(1)",
        "source": "mercadolivre.com.br",
    }
    result = validator.validate(
        step_name="json_ld_parser",
        payload=payload,
        url="https://mercadolivre.com.br/MLB-123",
        source="mercadolivre.com.br",
    )

    assert result.is_valid
    assert result.payload is not None
    assert result.payload["url"] == "https://mercadolivre.com.br/MLB-123"

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
        "availability": None,
        "last_status": None,
        "currency": None,
    }

def test_validator_records_invalid_price() -> None:
    validator = DataQualityValidator()
    result = validator.validate(
        step_name="html_metadata_parser",
        payload={"name": "Produto", "current_price": "abc", "url": ""},
        url="https://exemplo.com/produto",
        source="exemplo.com",
    )
    assert result.is_valid
    assert result.payload == {
        "name": "Produto",
        "current_price": None,
        "url": "https://exemplo.com/produto",
        "source": "exemplo.com",
        "availability": None,
        "last_status": "price_inferred_null",
        "currency": None,
    }

def test_validator_records_domain_from_full_source() -> None:
    validator = DataQualityValidator()
    result = validator.validate(
        step_name="html_metadata_parser",
        payload={"name": "Produto", "current_price": "abc", "url": ""},
        url="https://exemplo.com/produto",
        source="https://loja.teste.com/oferta",
    )
    assert result.is_valid
    assert result.payload == {
        "name": "Produto",
        "current_price": None,
        "url": "https://exemplo.com/produto",
        "source": "loja.teste.com",
        "availability": None,
        "last_status": "price_inferred_null",
        "currency": None,
    }

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
    payload = {"name": "", "current_price": "abc", "url": ""}

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
    assert log_entry["reason_code"] == "name_missing"
    assert log_entry["parser_name"] == "html_metadata_parser"
    assert log_entry["dump_path"] == "/tmp/dump.html"
    