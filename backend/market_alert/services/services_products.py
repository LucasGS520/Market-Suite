""" Conversores e validações para contratos simplificados de produtos.

As respostas de produtos monitorados e concorrentes foram reduzidas ao
mínimo necessário: identificador, URL, nome, preço obrigatório,
timestamp da coleta e origem. Os helpers abaixo evitam espalhar lógicas
de fallback ou mensagens de erro inconsistentes pelas rotas.
"""

from decimal import Decimal
from typing import Literal
from urllib.parse import urlparse

from fastapi import HTTPException, status

from market_alert.enums.enums_products import MonitoredStatus, ProductStatus
from market_alert.enums.enums_comparisons import CompetitivenessStatus
from market_alert.models.models_comparisons import PriceComparisonSummary
from market_alert.models.models_products import CompetitorProduct, MonitoredProduct
from market_alert.schemas.schemas_comparisons import PriceComparisonSummaryResponse
from market_alert.schemas.schemas_products import (
    CompetitorProductResponse,
    MonitoredProductResponse,
)
from shared.utils import sanitize_text


def _ensure_price(
    value: Decimal | None,
    context: str,
    *,
    allow_missing_price: bool = False
) -> Decimal | None:
    """Garante presença do preço antes de expor o produto ao frontend.

    Quando o preço ainda não foi coletado e a chamada tolera itens pendentes,
    o valor é propagado como ``None`` para que a camada superior indique o
    estado de scraping em andamento.
    """

    if value is None and not allow_missing_price:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"O produto {context} ainda não possui preço coletado. "
            ),
        )
    return value


def build_monitored_response(
    monitored: MonitoredProduct,
    summary: PriceComparisonSummary | None = None,
    *,
    allow_missing_price: bool = False,
) -> MonitoredProductResponse:
    """Converte um monitorado em contrato simplificado com preço obrigatório.

    Quando disponível, inclui status de competitividade calculado a partir do
    último resumo armazenado para o produto.
    """
    current_price = _ensure_price(monitored.current_price, "monitorado", allow_missing_price=allow_missing_price)
    availability = None
    if monitored.status in {MonitoredStatus.active, MonitoredStatus.pending}:
        availability = True
    elif monitored.status == MonitoredStatus.failed:
        availability = False

    competitiveness_status: CompetitivenessStatus | None = None
    comparison_summary: PriceComparisonSummaryResponse | None = None
    if summary and summary.aggregates:
        competitiveness_value = summary.aggregates.get("competitiveness_status")
        if competitiveness_value:
            try:
                competitiveness_status = CompetitivenessStatus(competitiveness_value)
            except ValueError:
                #Ignora valores inesperados no agregado para não quebrar o contrato
                competitiveness_status = None

        from market_alert.services.services_comparison import _extract_competitors_count, build_comparison_summary
        #Reutiliza a normalização padrão para evitar formatos divergentes no frontend
        normalized_summary = build_comparison_summary(
            None,
            competitors_count=_extract_competitors_count(summary),
            stored_summary=summary,
        )

        comparison_summary = PriceComparisonSummaryResponse(
            monitored_product_id=monitored.id,
            **normalized_summary,
        )

    return MonitoredProductResponse(
        id=monitored.id,
        owner_id=monitored.user_id,
        display_name=monitored.display_name,
        name=monitored.display_name,
        url=monitored.product_url,
        current_price=current_price,
        currency=monitored.currency,
        collected_at=monitored.collected_at,
        source="monitored",
        availability=availability,
        last_status=monitored.status.value,
        last_scraped_at=monitored.last_scraped_at,
        thumbnail=monitored.thumbnail,
        competitiveness_status=competitiveness_status,
        comparison_summary=comparison_summary,
        is_featured=monitored.is_featured,
    )


def _friendly_name_from_url(url: str) -> str:
    """ Deriva nome amigável usando host, evitando expor identificadores internos """
    parsed = urlparse(url)
    hostname = sanitize_text(parsed.hostname or parsed.netloc)
    if hostname:
        return hostname
    
    fallback = sanitize_text(url)
    return fallback or "Concorrente"

def build_competitor_response(
    competitor: CompetitorProduct,
    *,
    source: Literal["competitor"] = "competitor",
    allow_missing_price: bool = False,
) -> CompetitorProductResponse:
    """ Converte um concorrente em contrato simplificado com preço obrigatório """

    current_price = _ensure_price(competitor.current_price, "concorrente", allow_missing_price=allow_missing_price)
    availability = None
    if competitor.status == ProductStatus.available:
        availability = True
    elif competitor.status == ProductStatus.unavailable:
        availability = False

    sanitized_display_name = sanitize_text(competitor.display_name)
    friendly_name = sanitized_display_name or _friendly_name_from_url(competitor.product_url)

    return CompetitorProductResponse(
        id=competitor.id,
        monitored_product_id=competitor.monitored_product_id,
        display_name=sanitized_display_name or friendly_name,
        name=friendly_name,
        url=competitor.product_url,
        current_price=current_price,
        currency=competitor.currency,
        collected_at=competitor.collected_at,
        source=source,
        availability=availability,
        last_status=competitor.status.value,
        is_paused=competitor.is_paused,
    )
