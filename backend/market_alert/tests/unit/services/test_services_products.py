""" Testes para garantir nomes amigáveis de concorrentes na resposta """

from datetime import datetime, timezone
from decimal import Decimal
from uuid import uuid4

from market_alert.enums.enums_products import ProductStatus
from market_alert.models.models_products import CompetitorProduct
from market_alert.services.services_products import build_competitor_response


def _build_competitor(**overrides) -> CompetitorProduct:
    """Monta instâncias de concorrente com valores padrão para os testes."""
    return CompetitorProduct(
        id=overrides.get("id", uuid4()),
        monitored_product_id=overrides.get("monitored_product_id", uuid4()),
        name_competitor=overrides.get("name_competitor", ""),
        product_url=overrides.get("product_url", "https://example.com/produto"),
        current_price=overrides.get("current_price", Decimal("10.00")),
        old_price=overrides.get("old_price"),
        free_shipping=overrides.get("free_shipping", False),
        seller=overrides.get("seller"),
        seller_rating=overrides.get("seller_rating"),
        currency=overrides.get("currency"),
        thumbnail=overrides.get("thumbnail"),
        status=overrides.get("status", ProductStatus.available),
        is_paused=overrides.get("is_paused", False),
        last_checked=overrides.get("last_checked", datetime.now(timezone.utc)),
        updated_at=overrides.get("updated_at", datetime.now(timezone.utc)),
        created_at=overrides.get("created_at", datetime.now(timezone.utc)),
    )


def test_build_competitor_response_uses_hostname_fallback() -> None:
    """Garante que um nome vazio gera fallback amigável com hostname."""
    competitor = _build_competitor(
        name_competitor=" ",
        product_url="https://loja.example.com/oferta",
    )

    response = build_competitor_response(competitor, allow_missing_price=True)

    assert response.name == "loja.example.com"


def test_build_competitor_response_keeps_display_name() -> None:
    """Confirma que nomes sanitizados fornecidos pelo usuário são respeitados."""
    competitor = _build_competitor(
        name_competitor=" Concorrente VIP ",
        product_url="https://example.com/item",
    )

    response = build_competitor_response(competitor, allow_missing_price=True)

    assert response.name == "Concorrente VIP"