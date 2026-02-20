""" Conversores e validações para contratos simplificados de produtos.

As respostas de produtos monitorados e concorrentes foram reduzidas ao
mínimo necessário: identificador, URL, nome, preço obrigatório,
timestamp da coleta e origem. Os helpers abaixo evitam espalhar lógicas
de fallback ou mensagens de erro inconsistentes pelas rotas.
"""

from decimal import Decimal
from datetime import datetime, timezone
from typing import Literal
from urllib.parse import urlparse

from fastapi import HTTPException, status

from market_alert.enums.enums_products import MonitoredStatus, ProductStatus
from market_alert.enums.enums_comparisons import CompetitivenessStatus
from market_alert.models.models_comparisons import PriceComparisonSummary
from market_alert.models.models_products import CompetitorProduct, MonitoredProduct
from market_alert.schemas.schemas_comparisons import PriceComparisonSummaryResponse
from market_alert.schemas.schemas_products import CompetitorProductResponse, MonitoredProductResponse
from market_alert.utils.product_stats_formatter import get_product_stats
from shared.utils import sanitize_text


def _normalize_timestamp(value: datetime | None) -> datetime | None:
    """ Normaliza timestamp para UTC preservando valores nulos """
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)

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

def _resolve_display_status(
    *,
    monitored: MonitoredProduct,
    availability: bool | None,
    current_price: Decimal | None,
    summary: PriceComparisonSummaryResponse | None,
    competitiveness_status: CompetitivenessStatus | None,
) -> str:
    """ Consolida o status exibido priorizando indisponibilidade e pausa. """
    normalized_last_status = (monitored.last_status or "").strip().lower()
    unavailable_signals = {"unavailable", "removed", "sold_out"}

    if availability is False or normalized_last_status in unavailable_signals:
        return "inactive"

    if monitored.status == MonitoredStatus.inactive and availability is not False:
        return "paused"

    if summary and getattr(summary, "ignored_due_to_inactive", False):
        return "inactive"

    if not monitored.last_scraped_at and current_price is None:
        return "collecting"

    if availability is True and current_price is None:
        return "no_price"

    competitors_with_price = 0
    competitors_total = 0
    if summary:
        competitors_with_price = summary.competitors_with_price_count or 0
        competitors_total = summary.competitors_count or 0

    if competitors_with_price <= 0 and competitors_total <= 0:
        return "no_competitors"
    if competitors_with_price <= 0:
        return "no_competitors"

    if competitiveness_status == CompetitivenessStatus.COMPETITIVE:
        return "competitive"
    if competitiveness_status == CompetitivenessStatus.ATTENTION:
        return "attention"
    if competitiveness_status == CompetitivenessStatus.URGENT:
        return "urgent"

    return "unknown"

def build_monitored_response(
    monitored: MonitoredProduct,
    summary: PriceComparisonSummary | None = None,
    *,
    allow_missing_price: bool = False,
    last_price_change_at: datetime | None = None,
    global_last_price_change_at: datetime | None = None,
) -> MonitoredProductResponse:
    """Converte um monitorado em contrato simplificado com preço obrigatório.

    Quando disponível, inclui status de competitividade calculado a partir do
    último resumo armazenado para o produto. A data da última mudança de preço
    é propagada tanto no campo legado quanto no campo global para manter
    compatibilidade com consumidores existentes.último resumo armazenado para o produto.
    """
    current_price = _ensure_price(monitored.current_price, "monitorado", allow_missing_price=allow_missing_price)
    availability = monitored.availability
    if availability is None:
        if monitored.status in {MonitoredStatus.active, MonitoredStatus.pending}:
            availability = True
        elif monitored.status == MonitoredStatus.failed:
            availability = False

    competitiveness_status: CompetitivenessStatus | None = None
    comparison_summary: PriceComparisonSummaryResponse | None = None
    
    #summary pode ser um ORM PriceComparisonSummary OU um dict já normalizado
    normalized_summary: dict | None = None
    if summary is not None:
        #Caso já recebamos um dict (ex.: _refresh_stale_summary_if_needed), use direto
        if isinstance(summary, dict):
            normalized_summary = summary
        else:
            #summary é um objeto ORM PriceComparisonSummary (possui .aggregates)
            #Reutiliza a normalização padrão para evitar formatos divergentes no frontend
            from market_alert.services.services_comparison import summarize_comparison

            normalized_summary = summarize_comparison(
                None,
                summary,
            )
    
    if normalized_summary:
        competitiveness_value = normalized_summary.get("competitiveness_status")
        if competitiveness_value:
            try:
                competitiveness_status = CompetitivenessStatus(competitiveness_value)
            except ValueError:
                #Ignora valores inesperados no agregado para não quebrar o contrato
                competitiveness_status = None

        comparison_summary = PriceComparisonSummaryResponse(
            monitored_product_id=monitored.id,
            **normalized_summary,
        )

    stats_payload = get_product_stats(monitored)
    #Prioriza datas informadas pelo fluxo de comparação, mas mantém fallback do modelo
    resolved_last_change = _normalize_timestamp(
        global_last_price_change_at or last_price_change_at or stats_payload.get("last_price_change_at")
    )

    normalized_last_status = monitored.last_status or monitored.status.value

    display_status = _resolve_display_status(
        monitored=monitored,
        availability=availability,
        current_price=current_price,
        summary=comparison_summary,
        competitiveness_status=competitiveness_status,
    )

    return MonitoredProductResponse(
        id=monitored.id,
        owner_id=monitored.user_id,
        display_name=monitored.display_name,
        name=monitored.display_name,
        url=monitored.product_url,
        current_price=current_price,
        currency=monitored.currency,
        source="monitored",
        display_status=display_status,
        availability=availability,
        last_status=normalized_last_status,
        last_checked=_normalize_timestamp(monitored.last_checked),
        thumbnail=monitored.thumbnail,
        created_at=_normalize_timestamp(monitored.created_at),
        last_scraped_at=_normalize_timestamp(monitored.last_scraped_at),
        last_collected_at=_normalize_timestamp(stats_payload.get("last_collected_at")),
        next_check_at=_normalize_timestamp(stats_payload.get("next_check_at")),
        stability=stats_payload.get("stability"),
        monitored_since=_normalize_timestamp(stats_payload.get("monitored_since")),
        paused=bool(getattr(monitored, "paused", False)),
        paused_at=_normalize_timestamp(getattr(monitored, "paused_at", None)),
        last_price_change_at=resolved_last_change,
        last_price_change_global_at=resolved_last_change,
        competitiveness_status=competitiveness_status,
        is_featured=monitored.is_featured,
        comparison_summary=comparison_summary,
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
    availability = competitor.availability
    if availability is None:
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
        last_scraped_at=_normalize_timestamp(competitor.last_scraped_at or competitor.last_checked or competitor.created_at),
        last_checked=_normalize_timestamp(competitor.last_checked),
        source=source,
        availability=availability,
        last_status=competitor.last_status,
        is_paused=competitor.is_paused,
    )
