""" Testes das funções puras de serviços de produtos """

from __future__ import annotations

from decimal import Decimal
from uuid import uuid4

from market_alert.enums.enums_products import MonitoringType, MonitoredStatus, ProductStatus
from market_alert.models.models_products import CompetitorProduct, MonitoredProduct
from market_alert.services.services_products import build_competitor_response, build_monitored_response


def test_build_monitored_response_minimo() -> None:
    """ Confirma que o contrato mínimo é montado para monitorados """
    monitorado = MonitoredProduct(
        id=uuid4(),
        user_id=uuid4(),
        name_identification="Produto Teste",
        monitoring_type=MonitoringType.scraping,
        product_url="https://exemplo.com/produto",
        normalized_url="https://exemplo.com/produto",
        current_price=Decimal("10.00"),
        currency="BRL",
        status=MonitoredStatus.active,
        is_featured=False,
    )

    resposta = build_monitored_response(monitorado, allow_missing_price=False)

    assert resposta.name == "Produto Teste"
    assert resposta.current_price == Decimal("10.00")
    assert resposta.display_status == "no_competitors"
    assert resposta.availability is True


def test_build_competitor_response_friendly_name() -> None:
    """ Garante que o nome amigável usa o host quando display_name está vazio """
    concorrente = CompetitorProduct(
        id=uuid4(),
        monitored_product_id=uuid4(),
        name_competitor=" ",
        product_url="https://loja.exemplo.com/item",
        current_price=Decimal("12.50"),
        currency="BRL",
        status=ProductStatus.available,
        is_paused=False,
    )

    resposta = build_competitor_response(concorrente, allow_missing_price=False)

    assert resposta.name == "loja.exemplo.com"
    assert resposta.current_price == Decimal("12.50")
    