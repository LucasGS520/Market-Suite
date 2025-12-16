""" Garante validação e valores padrão dos esquemas de produtos compartilhados """

from decimal import Decimal

import pytest
from pydantic import ValidationError

from backend.shared.schemas.shared_schemas_products import (
    InitialCompetitorCreateScraping,
    MonitoredProductCreateScraping,
    MonitoredScrapedInfo,
    CompetitorProductCreateScraping,
    CompetitorScrapedInfo,
)

def test_monitored_scraped_info_defaults():
    data = MonitoredScrapedInfo(
        name="Produto monitorado",
        product_url="https://example.com/produto",
        current_price=Decimal("10.5"),
    )
    assert data.thumbnail is None
    assert data.free_shipping is False
    assert data.source == "monitored"
    assert data.collected_at is not None

def test_competitor_scraped_info_defaults():
    data = CompetitorScrapedInfo(
        name="Produto",
        product_url="https://example.com/produto",
        current_price=Decimal("9.99"),
    )
    assert data.old_price is None
    assert data.thumbnail is None
    assert data.free_shipping is False
    assert data.seller is None
    assert data.seller_rating is None
    assert data.source == "competitor"

def test_monitored_product_required_fields():
    with pytest.raises(ValidationError) as exc:
        MonitoredProductCreateScraping()

    mensagens = str(exc.value)
    assert "product_url" in mensagens

def test_monitored_product_optional_name():
    data = MonitoredProductCreateScraping(
        product_url="https://example.com/produto",
    )
    assert data.name_identification is None

def test_monitored_product_blank_name_becomes_none():
    data = MonitoredProductCreateScraping(
        name_identification="   ",
        product_url="https://example.com/produto",
    )
    assert data.name_identification is None

def test_monitored_product_accepts_initial_competitor():
    competitor = InitialCompetitorCreateScraping(
        product_url="https://example.com/concorrente",
        name=" Loja teste ",
    )
    data = MonitoredProductCreateScraping(
        product_url="https://example.com/produto",
        initial_competitor=competitor,
    )

    assert data.initial_competitor is not None
    assert data.initial_competitor.name == "Loja teste"

def test_monitored_product_invalid_url():
    with pytest.raises(ValidationError) as exc:
        MonitoredProductCreateScraping(
            name_identification="Teste",
            product_url="nao-e-url",
        )
    assert "url" in str(exc.value).lower()

def test_competitor_product_invalid_url():
    from uuid import uuid4

    with pytest.raises(ValidationError) as exc:
        CompetitorProductCreateScraping(
            monitored_product_id=uuid4(),
            product_url="url-invalida",
        )
    assert "url" in str(exc.value).lower()

def test_competitor_product_optional_name():
    from uuid import uuid4

    payload = CompetitorProductCreateScraping(
        monitored_product_id=uuid4(),
        product_url="https://example.com/produto",
        name=" Concorrente Teste ",
    )

    assert payload.name == "Concorrente Teste"


def test_competitor_product_blank_name_becomes_none():
    from uuid import uuid4

    payload = CompetitorProductCreateScraping(
        monitored_product_id=uuid4(),
        product_url="https://example.com/produto",
        name="   ",
    )

    assert payload.name is None

def test_initial_competitor_blank_name_becomes_none():
    payload = InitialCompetitorCreateScraping(
        product_url="https://example.com/concorrente",
        name="   ",
    )

    assert payload.name is None
