""" Serviço de comparação e persistência de preços

O fluxo mantém apenas as etapas essenciais: carregamento de produtos,
execução da comparação e armazenamento do último resumo para consumo do
frontend.
"""

from uuid import UUID
from sqlalchemy.orm import Session
from fastapi import HTTPException, status
from fastapi.encoders import jsonable_encoder
from typing import Dict, Any, Optional, List
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
import structlog
import time
import json

from shared.metrics.metrics_price_comparison import (
    MALFORMED_COMPARISON_PAYLOADS_TOTAL,
    PRICE_COMPARISON_DURATION_SECONDS,
    PRICE_COMPARISON_FAILURES_TOTAL,
    PRICE_COMPARISONS_TOTAL,
    COMPARISONS_NO_AVAILABLE_COMPETITORS_TOTAL,
)

from market_alert.crud.crud_monitored import get_monitored_product_by_id
from market_alert.crud.crud_competitor import get_competitors_by_monitored_id
from market_alert.crud.crud_comparison import (
    create_price_comparison,
    get_comparison_by_id,
    get_latest_comparisons_for_products,
    get_latest_summary,
    paginate_comparisons,
    upsert_price_comparison_summary,
)
from market_alert.models.models_comparisons import PriceComparison, PriceComparisonSummary
from market_alert.models.models_products import CompetitorProduct
from market_alert.enums.enums_products import MonitoredStatus, ProductStatus
from market_alert.models import User
from market_alert.schemas.schemas_comparisons import (
    PaginatedPriceComparisonResponse,
    PriceComparisonResponse,
    PriceComparisonSummaryResponse,
)
from market_alert.utils.price_comparator import compare_prices
from market_alert.core.config_alert import settings
from market_alert.enums.enums_comparisons import CompetitivenessStatus
from market_alert.services.services_access import ensure_user_can_access_monitored


logger = structlog.get_logger("comparison_service")

#Limiares em porcentagem para classificar a competitividade frente ao menor preço.
COMPETITIVENESS_NON_COMPETITIVE_PCT = Decimal("1")  # Até 1% -> atenção (anteriormente 'nao_competitivo')
COMPETITIVENESS_ATTENTION_PCT = Decimal("5")      #>1% até 5% -> atencao

def ensure_user_can_view_monitored(
    *, db: Session, monitored_id: UUID, user: User
):
    """ Valida se o monitorado pertence ao usuário autenticado """
    return ensure_user_can_access_monitored(
        db=db,
        product_id=monitored_id,
        user=user,
        context={"monitored_id": str(monitored_id)},
    )

def get_paginated_comparisons_for_user(
    *,
    db: Session,
    monitored_id: UUID,
    user: User,
    page: int,
    per_page: int,
) -> PaginatedPriceComparisonResponse:
    """ Monta envelope paginado de comparações garantindo propriedade do monitorado """
    ensure_user_can_view_monitored(db=db, monitored_id=monitored_id, user=user)
    total, comparisons = paginate_comparisons(
        db, monitored_product_id=monitored_id, page=page, per_page=per_page
    )

    #Preenche o schema de resposta já com a estrutura de paginação esperada pelo frontend
    return PaginatedPriceComparisonResponse(
        items=comparisons,
        meta={"total": total, "page": page, "per_page": per_page},
    )

def get_comparison_summary_for_user(
    *, db: Session, monitored_id: UUID, user: User
) -> PriceComparisonSummaryResponse:
    """Retorna o resumo mais recente garantindo que o produto pertença ao usuário."""
    ensure_user_can_view_monitored(db=db, monitored_id=monitored_id, user=user)

    stored_summary = get_latest_summary(db, monitored_product_id=monitored_id)
    comparison = None

    competitors_count = _extract_competitors_count(stored_summary)

    if stored_summary and stored_summary.comparison_id:
        comparison = get_comparison_by_id(db, stored_summary.comparison_id)

    normalized_summary = build_comparison_summary(
        comparison,
        competitors_count=competitors_count,
        stored_summary=stored_summary,
    )

    return PriceComparisonSummaryResponse(monitored_product_id=monitored_id, **normalized_summary)

def get_comparison_detail_for_user(
    *,
    db: Session,
    comparison_id: UUID,
    user: User,
) -> PriceComparisonResponse:
    """Retorna detalhes de comparação apenas quando pertence ao usuário."""
    comparison = get_comparison_by_id(db, comparison_id)
    if comparison is None:
        #Oculta a existência do recurso quando inexistente
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Comparação não encontrada.",
        )

    ensure_user_can_view_monitored(
        db=db, monitored_id=comparison.monitored_product_id, user=user
    )

    return comparison

def run_price_comparison(
    db: Session,
    monitored_id: UUID,
    tolerance: Decimal | None = None,
) -> Dict[str, Any]:
    """Executa a comparação de preços retornando apenas o resumo essencial.

    O fluxo evita cálculos derivados quando já trabalhamos com resumos pré-existentes
    e persiste o payload completo somente quando configurado para depuração.
    """
    start = time.time()
    status = "success"
    result: Dict[str, Any] | None = None

    try:
        #Carrega o produto monitorado para validação
        monitored = get_monitored_product_by_id(db, monitored_id)
        if not monitored:
            raise ValueError(f"Monitored product {monitored_id} not found")

        #Recupera concorrentes associados
        competitors = get_competitors_by_monitored_id(
            db, monitored_id, include_paused=True, include_inactive=True
        )
        competitors = _deduplicate_competitors(competitors)
        
        available_competitors = [
            competitor
            for competitor in competitors
            if competitor.current_price is not None
            and competitor.availability is not False
            and getattr(competitor, "status", ProductStatus.available)
            not in {ProductStatus.unavailable, ProductStatus.removed}
            and not getattr(competitor, "is_paused", False)
        ]

        filtered_out = len(competitors) - len(available_competitors)
        if filtered_out:
            logger.info(
                "comparison_filtered_competitors", filtered=filtered_out, total=len(competitors)
            )

        inactive_reason = _resolve_monitored_inactive_reason(monitored)
        if inactive_reason:
            logger.info(
                "comparison_skipped_inactive_monitored",
                monitored_id=str(monitored_id),
                reason=inactive_reason,
                competitors_count=len(available_competitors),
            )
            payload_stub = {
                "monitored_price": None,
                "discrepancies": [],
                "lowest_competitor": None,
                "highest_competitor": None,
                "reason": inactive_reason,
                "ignored_due_to_inactive": True,
            }
            comparison = create_price_comparison(db, monitored.id, payload_stub)
            summary_payload = _apply_summary_defaults(
                payload_stub,
                timestamp=comparison.timestamp,
                comparison_id=comparison.id,
                competitors_count=len(available_competitors),
            )
            summary_payload["competitors_with_price_count"] = 0
            summary_payload["competitiveness_status"] = None
            summary_payload["comparison_insights"] = None
            summary_payload["ignored_due_to_inactive"] = True

            encoded_summary = jsonable_encoder(summary_payload)
            upsert_price_comparison_summary(
                db,
                monitored.id,
                comparison.id,
                encoded_summary,
            )
            encoded_result = {
                "summary": encoded_summary,
                "comparison_id": str(comparison.id),
                "monitored_id": str(monitored.id),
                "user_id": str(monitored.user_id),
                "lowest_competitor": None,
                "highest_competitor": None,
            }
            result = encoded_result
            return result

        if not available_competitors:
            COMPARISONS_NO_AVAILABLE_COMPETITORS_TOTAL.inc()

        logger.info(
            "comparison_started",
            monitored_id=str(monitored_id),
            competitors_count=len(available_competitors),
        )

        tol = tolerance if tolerance is not None else Decimal(str(settings.PRICE_TOLERANCE))

        #Processa comparação e persiste resultado
        raw_result = compare_prices(monitored, available_competitors, tol)
        encoded_result = jsonable_encoder(raw_result)

        persist_raw_result = getattr(settings, "COMPARISON_STORE_RAW_RESULT", False)
        stored_payload = (
            encoded_result
            if persist_raw_result
            else {
                "monitored_price": encoded_result.get("monitored_price"),
                "discrepancies": encoded_result.get("discrepancies", []),
                "lowest_competitor": encoded_result.get("lowest_competitor"),
                "highest_competitor": encoded_result.get("highest_competitor"),
            }
        )

        comparison = create_price_comparison(db, monitored.id, stored_payload)
        summary_payload = _build_summary_from_result(
            encoded_result,
            timestamp=comparison.timestamp,
            comparison_id=comparison.id,
            competitors_count=len(available_competitors),
        )
        encoded_summary = jsonable_encoder(summary_payload)
        if not available_competitors:
            encoded_summary["reason"] = encoded_summary.get("reason") or "no_available_competitors"
        upsert_price_comparison_summary(
            db,
            monitored.id,
            comparison.id,
            encoded_summary,
        )
        encoded_result["summary"] = encoded_summary
        encoded_result["comparison_id"] = str(comparison.id)
        encoded_result["monitored_id"] = str(monitored.id)
        encoded_result["user_id"] = str(monitored.user_id)
        result = encoded_result
        logger.info("comparison_finished", monitored_id=str(monitored_id))

    except Exception:
        status = "failure"
        raise

    finally:
        duration = time.time() - start
        #Registra métricas de duração e status
        PRICE_COMPARISON_DURATION_SECONDS.observe(duration)
        PRICE_COMPARISONS_TOTAL.labels(status=status).inc()

    return result

def _deduplicate_competitors(competitors: List[CompetitorProduct]) -> List[CompetitorProduct]:
    """Remove duplicidades simples mantendo o concorrente mais recente por ID """

    if not competitors:
        return []

    deduped: dict[str, CompetitorProduct] = {}
    for competitor in competitors:
        reference = str(getattr(competitor, "id", ""))
        if not reference:
            deduped[str(len(deduped))] = competitor
            continue

        existing = deduped.get(reference)
        if existing is None:
            deduped[reference] = competitor
            continue

        existing_checked = getattr(existing, "last_checked", None)
        current_checked = getattr(competitor, "last_checked", None)
        if existing_checked is None or (
            current_checked is not None and current_checked > existing_checked
        ):
            deduped[reference] = competitor

    return list(deduped.values())

def _to_decimal(value: Any) -> Optional[Decimal]:
    """ Converte valores do JSON armazenado para Decimal quando possível """
    if value is None:
        return None
    if isinstance(value, Decimal):
        return value
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        #Retorna None quando o valor não pode ser convertido sem perdas
        return None
    
def _extract_competitors_count(
    stored_summary: PriceComparisonSummary | None,
) -> int:
    """ Obtém a contagem de concorrentes a partir dos agregados persistidos.

    O campo ``competitors_count`` é armazenado no JSON ``aggregates`` e não
    como atributo direto do modelo. A extração defensiva evita ``AttributeError``
    quando o snapshot foi salvo sem este campo ou com tipos inesperados.
    """
    if stored_summary is None:
        return 0

    aggregates = stored_summary.aggregates if isinstance(stored_summary.aggregates, dict) else {}

    try:
        return int(aggregates.get("competitors_count", 0))
    except (TypeError, ValueError):
        #Padroniza a contagem em zero quando o valor não puder ser interpretado como inteiro
        return 0
    
def _empty_summary(competitors_count: int) -> Dict[str, Any]:
    """ Cria estrutura base do resumo competitivo com valores padrão """
    return {
        "comparison_id": None,
        "last_comparison_at": None,
        "computed_at": None,
        "monitored_price": None,
        "competitors_count": competitors_count,
        "competitors_with_price_count": 0,
        "competitors_mean": None,
        "competitors_min": None,
        "competitors_max": None,
        "position_rank": None,
        "potential_adjustment": None,
        "ignored_due_to_inactive": False,
        "competitiveness_status": None,
        "comparison_insights": None,
        "discrepancies": [],
        "reason": None,
    }

def _calculate_competitiveness_status(
    monitored_price: Optional[Decimal],
    reference_price: Optional[Decimal],
) -> Optional[str]:
    """ Define o status competitivo comparando o preço monitorado com o menor preço conhecido.

    A lógica segue as faixas solicitadas: diferenças menores ou iguais a zero
    são competitivas, positivas até 1% são ``nao_competitivas``, de 1% até 5%
    entram em ``atencao`` e acima de 5% tornam-se ``urgente``. Referências
    ausentes ou iguais a zero não são classificadas para evitar divisões
    inválidas.
    """
    if (
        monitored_price is None
        or reference_price is None
        or reference_price <= Decimal("0")
    ):
        return None

    #Se o monitorado for menor ou igual ao menor concorrente, é competitivo
    if monitored_price <= reference_price:
        return CompetitivenessStatus.COMPETITIVE.value

    #Calcula delta fractional e percentual com precisão para evitar que arredondamentos prejudiquem a classificação.
    try:
        delta_fraction = (monitored_price - reference_price) / reference_price
    except (InvalidOperation, ZeroDivisionError):
        return None

    if delta_fraction <= Decimal("0"):
        return CompetitivenessStatus.COMPETITIVE.value

    #Percentual em termos de porcentagem (ex.: 1.23 = 1.23%)
    percentage = (delta_fraction * Decimal("100")).quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)

    # Aplicar faixas: >0% até 1% => atenção (anteriormente 'nao_competitivo');
    # >1% até 5% => atenção; >5% => urgente.
    # Observação: mantemos os mesmos limites percentuais, mas unificamos
    # o rótulo de até 5% como 'atencao'. Retornamos explicitamente ATTENTION
    # para garantir consistência independentemente do nome do membro enum.
    if percentage > Decimal("0") and percentage <= COMPETITIVENESS_NON_COMPETITIVE_PCT:
        return CompetitivenessStatus.ATTENTION.value
    if percentage <= COMPETITIVENESS_ATTENTION_PCT:
        return CompetitivenessStatus.ATTENTION.value
    return CompetitivenessStatus.URGENT.value

def _build_summary_from_result(
    payload: Dict[str, Any] | None,
    *,
    timestamp: Any,
    comparison_id: UUID | None,
    competitors_count: int,
) -> Dict[str, Any]:
    """ Monta um resumo completo a partir do resultado do comparador.

    A lógica reaproveita o cálculo detalhado para garantir que média,
    mínimos, ranking e ajuste potencial sejam persistidos sempre que
    o endpoint de comparação for chamado.
    """
    if not isinstance(payload, dict):
        logger.warning(
            "comparison_payload_invalid_type",
            expected="dict",
            received_type=type(payload).__name__,
            comparison_id=str(comparison_id) if comparison_id else None,
        )
        MALFORMED_COMPARISON_PAYLOADS_TOTAL.labels(stage="build_summary").inc()
        payload_dict: dict[str, Any] = {}
    else:
        payload_dict = payload

    detailed_summary = _compute_summary_from_payload(
        payload_dict,
        timestamp=timestamp,
        comparison_id=comparison_id,
        competitors_count=competitors_count,
    )

    return _apply_summary_defaults(
        detailed_summary,
        timestamp=timestamp,
        comparison_id=comparison_id,
        competitors_count=competitors_count,
    )

def _compute_summary_from_payload(
    payload: Dict[str, Any] | None,
    *,
    timestamp: Any,
    comparison_id: UUID | None,
    competitors_count: int,
) -> Dict[str, Any]:
    """ Calcula o resumo competitivo a partir do payload cru armazenado.

    O cálculo utiliza todos os preços convertidos via ``_to_decimal`` e aplica:
    - ``competitors_mean``: média aritmética dos preços dos concorrentes (2 casas decimais, ``ROUND_HALF_UP``)
    - ``competitors_min``/``competitors_max``: menor e maior preço conhecido
    - ``position_rank``: 1 + quantidade de concorrentes com preço menor que o monitorado
    - ``potential_adjustment``: diferença absoluta entre o preço monitorado e o menor preço concorrente quando o monitorado está acima (2 casas decimais,``ROUND_HALF_UP``)

    Requer ao menos um preço de concorrente e um preço monitorado para gerar ranking, ajuste potencial e insights textuais. 
    Em cenários sem preços suficientes, os campos permanecem nulos para sinalizar ausência de dados.
    """
    summary = _empty_summary(competitors_count)
    summary["last_comparison_at"] = timestamp
    summary["computed_at"] = timestamp
    if comparison_id is not None:
        summary["comparison_id"] = str(comparison_id)

    if not isinstance(payload, dict):
        MALFORMED_COMPARISON_PAYLOADS_TOTAL.labels(stage="compute_summary").inc()
        logger.warning(
            "comparison_payload_invalid",
            comparison_id=str(comparison_id) if comparison_id else None,
        )
        return summary

    try:
        discrepancies_raw = payload.get("discrepancies") or []
        summary["discrepancies"] = (
            discrepancies_raw if isinstance(discrepancies_raw, list) else []
        )
        monitored_price = _to_decimal(payload.get("monitored_price"))

        summary["ignored_due_to_inactive"] = bool(payload.get("ignored_due_to_inactive"))
        reason = payload.get("reason") or summary.get("reason")
        if reason:
            summary["reason"] = reason

        if monitored_price is not None:
            summary["monitored_price"] = monitored_price
        competitor_prices: list[Decimal] = []

        def _append_price(value: Any) -> None:
            price = _to_decimal(value)
            if price is not None and price not in competitor_prices:
                competitor_prices.append(price)

        for item in summary["discrepancies"]:
            if isinstance(item, dict):
                _append_price(item.get("price"))

        lowest_raw = payload.get("lowest_competitor") or {}
        highest_raw = payload.get("highest_competitor") or {}
        lowest_price = _to_decimal(lowest_raw.get("price"))
        highest_price = _to_decimal(highest_raw.get("price"))

        _append_price(lowest_price)
        _append_price(highest_price)

        summary["competitors_with_price_count"] = len(competitor_prices)

        if summary["ignored_due_to_inactive"]:
            summary["competitiveness_status"] = None
            summary["comparison_insights"] = None
            return summary

        if competitor_prices:
            competitors_min = min(competitor_prices)
            competitors_max = max(competitor_prices)
            competitors_mean = (
                sum(competitor_prices) / len(competitor_prices)
            ).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

            summary["competitors_min"] = competitors_min
            summary["competitors_max"] = competitors_max
            summary["competitors_mean"] = competitors_mean

        if (
            monitored_price is not None
            and summary.get("competitors_min") is not None
            and monitored_price > summary.get("competitors_min")
        ):
            summary["potential_adjustment"] = (
                monitored_price - summary.get("competitors_min")
            ).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

        if monitored_price is not None and competitor_prices:
            cheaper_count = sum(1 for price in competitor_prices if price < monitored_price)
            summary["position_rank"] = cheaper_count + 1

        status_reference = summary.get("competitors_min")
        status = _calculate_competitiveness_status(monitored_price, status_reference)
        if status is not None:
            summary["competitiveness_status"] = status

        summary["comparison_insights"] = _build_comparison_insights(
            monitored_price=monitored_price,
            competitors_min=summary.get("competitors_min"),
            competitors_count=competitors_count,
            position_rank=summary.get("position_rank"),
            potential_adjustment=summary.get("potential_adjustment"),
            competitiveness_status=summary.get("competitiveness_status"),
        )
        return summary

    except (AttributeError, TypeError, ValueError) as exc:
        price_preview = None
        try:
            price_preview = json.dumps(payload)[:300]
        except Exception:
            price_preview = str(payload)[:300]
        PRICE_COMPARISON_FAILURES_TOTAL.labels(stage="compute_summary").inc()
        MALFORMED_COMPARISON_PAYLOADS_TOTAL.labels(stage="compute_summary").inc()
        logger.warning(
            "comparison_summary_failed",
            error=str(exc),
            comparison_id=str(comparison_id) if comparison_id else None,
            payload_preview=price_preview,
        )
        return summary

def _calculate_percentage_delta(
    monitored_price: Optional[Decimal], reference_price: Optional[Decimal]
) -> Optional[Decimal]:
    """ Calcula variação percentual entre o preço monitorado e uma referência.

    Retorna ``None`` quando algum dos valores é inexistente ou quando a
    referência é menor ou igual a zero para evitar divisões inválidas.
    """
    if (
        monitored_price is None
        or reference_price is None
        or reference_price <= Decimal("0")
    ):
        return None

    percentage_delta = (
        (monitored_price - reference_price) / reference_price
    ) * Decimal("100")
    return percentage_delta.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _build_comparison_insights(
    *,
    monitored_price: Optional[Decimal],
    competitors_min: Optional[Decimal],
    competitors_count: int,
    position_rank: Optional[int],
    potential_adjustment: Optional[Decimal],
    competitiveness_status: Optional[str],
) -> Optional[str]:
    """ Gera texto explicativo sobre competitividade e ajuste recomendado """
    if monitored_price is None:
        return "Preço do produto monitorado não disponível; recoletores em andamento."
    if competitors_min is None or position_rank is None or competitors_count is None:
        return None

    total_itens = competitors_count + 1 if competitors_count >= 0 else 1
    delta_vs_min = _calculate_percentage_delta(monitored_price, competitors_min)

    if delta_vs_min is None:
        return None

    adjustment_value = potential_adjustment or Decimal("0.00")
    adjustment_pct = None
    if potential_adjustment is not None and monitored_price > Decimal("0"):
        adjustment_pct = (
            (potential_adjustment / monitored_price) * Decimal("100")
        ).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    if adjustment_value <= 0:
        return (
            f"Preço alinhado ao menor concorrente (R${competitors_min}). "
            f"Posição atual: #{position_rank} de {total_itens}."
        )
    adjustment_suffix = f" (~{adjustment_pct}%)" if adjustment_pct is not None else ""
    status_hint = (
        f" Status: {competitiveness_status}." if competitiveness_status else ""
    )

    return (
        f"Você está {delta_vs_min}% acima do menor concorrente (R${competitors_min}). "
        f"Posição atual: #{position_rank} de {total_itens}. "
        f"Recomendação: reduzir R${adjustment_value}{adjustment_suffix} para igualar o menor preço."
        f"{status_hint}"
    )

def _apply_summary_defaults(
    payload: Dict[str, Any],
    *,
    timestamp: Any,
    comparison_id: UUID | None,
    competitors_count: int,
) -> Dict[str, Any]:
    """ Garante que o resumo persistido contenha todos os campos esperados """
    summary = _empty_summary(competitors_count)
    summary.update(payload or {})

    #Preserva o timestamp da última comparação quando já registrado no payload
    if summary.get("last_comparison_at") is None:
        summary["last_comparison_at"] = timestamp
    summary["computed_at"] = timestamp
    summary["competitors_count"] = competitors_count

    if summary.get("discrepancies") is None:
        summary["discrepancies"] = []

    if comparison_id is not None:
        summary["comparison_id"] = summary.get("comparison_id") or str(comparison_id)

    try:
        summary["competitors_with_price_count"] = int(summary["competitors_with_price_count"])
    except (TypeError, ValueError, KeyError):
        summary["competitors_with_price_count"] = 0

    summary["ignored_due_to_inactive"] = bool(summary.get("ignored_due_to_inactive"))

    if summary["ignored_due_to_inactive"]:
        summary["competitiveness_status"] = None
        summary["comparison_insights"] = None

    summary = _coerce_decimal_fields(summary)

    if summary.get("competitiveness_status") is None:
        monitored_price = summary.get("monitored_price")
        status_reference = summary.get("competitors_min")
        status = _calculate_competitiveness_status(monitored_price, status_reference)
        if status is not None:
            summary["competitiveness_status"] = status

    #Motivo explicíto para ausência de dados competitivos exibição na UI
    if not summary.get("reason"):
        no_competitors_available = competitors_count == 0 or summary.get(
            "competitors_with_price_count", 0
        ) == 0
        if no_competitors_available:
            summary["reason"] = "sem_concorrentes_disponiveis"

    return summary


def _coerce_decimal_fields(summary: Dict[str, Any]) -> Dict[str, Any]:
    """Normaliza campos monetários para Decimal para evitar strings na resposta"""

    monetary_keys = [
        "monitored_price",
        "competitors_mean",
        "competitors_min",
        "competitors_max",
        "potential_adjustment",
    ]

    for key in monetary_keys:
        if key in summary:
            summary[key] = _to_decimal(summary.get(key))

    return summary


def build_comparison_summary(
    comparison: PriceComparison | None,
    *,
    competitors_count: int,
    stored_summary: PriceComparisonSummary | None = None,
) -> Dict[str, Any]:
    """ Normaliza os dados de resumo para exposição na API pública """
    if stored_summary is not None:
        stored_payload = stored_summary.aggregates or {}
        recomputed_payload = _compute_summary_from_payload(
            stored_payload,
            timestamp=stored_summary.timestamp,
            comparison_id=stored_summary.comparison_id,
            competitors_count=competitors_count,
        )

        #Preferir valores recomputados quando disponíveis (sobrescrever snapshots antigos) 
        #Garantir que classificações reflitam os preços atuais sempre que houver dados novos.
        merged_payload = stored_payload.copy()
        for key, value in recomputed_payload.items():
            if value is None:
                continue
            
            if key == "last_comparison_at" and merged_payload.get(key) is not None:
                continue
            
            if (
                key == "competitors_with_price_count"
                and merged_payload.get(key)
                and value == 0
            ):
                continue
            
            merged_payload[key] = value

        return _apply_summary_defaults(
            merged_payload,
            timestamp=stored_summary.timestamp,
            comparison_id=stored_summary.comparison_id,
            competitors_count=competitors_count,
        )

    if comparison is None:
        summary = _empty_summary(competitors_count)
        if competitors_count == 0:
            summary["reason"] = "sem_concorrentes_disponiveis"
        return summary

    payload = comparison.data or {}

    if isinstance(payload, dict):
        embedded_summary = payload.get("summary")
        if isinstance(embedded_summary, dict):
            #Quando a comparação já armazena um resumo, evitamos cálculos adicionais
            return _apply_summary_defaults(
                embedded_summary,
                timestamp=comparison.timestamp,
                comparison_id=comparison.id,
                competitors_count=competitors_count,
            )

    return _compute_summary_from_payload(
        payload,
        timestamp=comparison.timestamp,
        comparison_id=comparison.id,
        competitors_count=competitors_count,
    )

def _resolve_monitored_inactive_reason(monitored: Any) -> str | None:
    """ Determina se o monitorado deve ser tratado como inativo na comparação """
    unavailable_statuses = {"unavailable", "removed", "sold_out"}
    last_status = (getattr(monitored, "last_status", None) or "").lower()
    availability = getattr(monitored, "availability", None)
    has_price = getattr(monitored, "current_price", None) is not None
    monitoring_status = getattr(monitored, "status", None)

    if availability is False:
        return "monitored_unavailable"
    if last_status in unavailable_statuses:
        return "monitored_unavailable"
    if monitoring_status == MonitoredStatus.inactive and not has_price:
        return "monitored_without_price"
    if not has_price:
        return "monitored_without_price"

    return None
