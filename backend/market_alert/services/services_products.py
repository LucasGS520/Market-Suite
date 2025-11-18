""" Conversores e validações para contratos simplificados de produtos.

As respostas de produtos monitorados e concorrentes foram reduzidas ao
mínimo necessário: identificador, URL, nome, preço obrigatório,
timestamp da coleta e origem. Os helpers abaixo evitam espalhar lógicas
de fallback ou mensagens de erro inconsistentes pelas rotas.
"""

from decimal import Decimal
from typing import Literal

from fastapi import HTTPException, status

from market_alert.enums.enums_products import MonitoredStatus, ProductStatus
from market_alert.models.models_products import CompetitorProduct, MonitoredProduct
from market_alert.schemas.schemas_products import (
    CompetitorProductResponse,
    MonitoredProductResponse,
)


def _ensure_price(value: Decimal | None, context: str) -> Decimal:
    """ Garante presença do preço antes de expor o produto ao frontend """
    if value is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"O produto {context} ainda não possui preço coletado. "
            ),
        )
    return value


def build_monitored_response(monitored: MonitoredProduct) -> MonitoredProductResponse:
    """ Converte um monitorado em contrato simplificado com preço obrigatório """
    current_price = _ensure_price(monitored.current_price, "monitorado")
    availability = None
    if monitored.status in {MonitoredStatus.active, MonitoredStatus.pending}:
        availability = True
    elif monitored.status == MonitoredStatus.failed:
        availability = False

    return MonitoredProductResponse(
        id=monitored.id,
        name=monitored.display_name,
        product_url=monitored.product_url,
        current_price=current_price,
        currency=monitored.currency,
        collected_at=monitored.collected_at,
        source="monitored",
        availability=availability,
        last_status=monitored.status.value,
    )


def build_competitor_response(
    competitor: CompetitorProduct,
    *,
    source: Literal["competitor"] = "competitor",
) -> CompetitorProductResponse:
    """ Converte um concorrente em contrato simplificado com preço obrigatório """

    current_price = _ensure_price(competitor.current_price, "concorrente")
    availability = None
    if competitor.status == ProductStatus.available:
        availability = True
    elif competitor.status == ProductStatus.unavailable:
        availability = False

    return CompetitorProductResponse(
        id=competitor.id,
        monitored_product_id=competitor.monitored_product_id,
        name=competitor.display_name,
        product_url=competitor.product_url,
        current_price=current_price,
        currency=competitor.currency,
        collected_at=competitor.collected_at,
        source=source,
        availability=availability,
        last_status=competitor.status.value,
        is_paused=competitor.is_paused,
    )
