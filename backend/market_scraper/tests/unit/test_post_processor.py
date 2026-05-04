from __future__ import annotations

from decimal import Decimal

from market_scraper.domain.dtos import AcquisitionTelemetry
from market_scraper.post_processing.processor import PostProcessor


def test_post_processor_normalizes_payload_and_preserves_acquisition():
    acquisition = AcquisitionTelemetry(
        layer_used="curl_cffi",
        fallback_taken=False,
        classification_reason="html_valid",
        http_status=404,
        anti_bot_detected=False,
        anti_bot_pattern=None,
        anti_bot_bypassed=False,
    )

    result = PostProcessor().run(
        {
            "name": "Console",
            "current_price": "1999.90",
            "source": "mercadolivre.com.br",
            "availability": True,
            "last_status": "in_stock",
            "seller": "Loja Oficial",
        },
        acquisition,
        "https://example.com/product",
        "example.com",
    )

    assert result.name == "Console"
    assert result.current_price == Decimal("1999.90")
    assert result.availability is True
    assert result.last_status == "in_stock"
    assert result.source == "mercadolivre.com.br"
    assert result.extra_fields["seller"] == "Loja Oficial"
    assert result.extra_fields["acquisition"]["http_status"] == 404
    assert "name" not in result.extra_fields


def test_post_processor_infers_unavailable_when_payload_has_no_availability():
    acquisition = AcquisitionTelemetry(
        layer_used="curl_cffi",
        fallback_taken=False,
        classification_reason="not_found",
        http_status=404,
        anti_bot_detected=False,
        anti_bot_pattern=None,
        anti_bot_bypassed=False,
    )

    result = PostProcessor().run(
        {"url": "https://example.com/product"},
        acquisition,
        "https://example.com/product",
        "example.com",
    )

    assert result.availability is False
    assert result.current_price is None
    assert result.is_useful is True
    assert result.extra_fields["acquisition"]["data_quality"] == "normal"


def _no_acquisition() -> AcquisitionTelemetry:
    return AcquisitionTelemetry(
        layer_used="curl_cffi",
        fallback_taken=False,
        classification_reason="html_valid",
        http_status=200,
        anti_bot_detected=False,
        anti_bot_pattern=None,
        anti_bot_bypassed=False,
    )


def test_post_processor_price_zero_produces_price_unavailable():
    """Preço <= 0 é descartado e sinaliza PRICE_UNAVAILABLE."""
    result = PostProcessor().run(
        {"name": "Produto X", "current_price": "0"},
        _no_acquisition(),
        "https://example.com/p",
        "example.com",
    )
    assert result.current_price is None
    assert result.last_status == "price_unavailable"
    assert result.is_useful is True



def test_post_processor_outofstock_clears_price():
    """OutOfStock: preço extraído é descartado — não é confiável para produto indisponível."""
    result = PostProcessor().run(
        {"name": "TV", "current_price": "2999.90", "availability": False},
        _no_acquisition(),
        "https://example.com/p",
        "example.com",
    )
    assert result.availability is False
    assert result.current_price is None
    assert result.last_status is None
    assert result.is_useful is True


def test_post_processor_outofstock_does_not_set_price_unavailable():
    """OutOfStock com preço descartado NÃO gera price_unavailable — contexto é OOS."""
    result = PostProcessor().run(
        {"name": "TV", "current_price": "2999.90", "availability": False},
        _no_acquisition(),
        "https://example.com/p",
        "example.com",
    )
    assert result.last_status is None  # não é "price_unavailable", é OOS
