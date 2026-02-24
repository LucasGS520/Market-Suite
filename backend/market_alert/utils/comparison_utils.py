""" Utilitários de carregamento e filtragem para comparação de preços

Responsabilidade: funções de suporte ao serviço de comparação que fazem I/O
(consultas ao banco), mas cada uma com uma única responsabilidade clara.

Separa do services_comparison.py:
- Carregamento de monitorado e filtragem de concorrentes
- Leitura do último snapshot persistido
- Resolução de preço com fallback em histórico
- Filtragem canônica de elegibilidade de concorrentes

Regras desta camada:
- Importa de: crud, models, enums, utils — nunca de services ou tasks
- Pode acessar banco de dados via Session
- Não contém lógica de cálculo de competitividade
- Não contém lógica de persistência de resultados
"""

from decimal import Decimal
from typing import Any, Dict, List, Optional, Tuple
from uuid import UUID

import structlog

from sqlalchemy import func
from sqlalchemy.orm import Session

from market_alert.crud.crud_monitored import get_monitored_product_by_id
from market_alert.crud.crud_competitor import get_competitors_by_monitored_id
from market_alert.crud.crud_comparison import get_latest_summary
from market_alert.crud.crud_price_history import get_latest_price_for_competitor
from market_alert.enums.enums_products import ProductStatus
from market_alert.models.models_comparisons import PriceComparisonSummary
from market_alert.models.models_products import CompetitorProduct
from market_alert.utils.price_decimal import to_decimal


logger = structlog.get_logger("comparison_utils")

__all__ = [
    "FilteredCompetitorsResult",
    "ComparisonCompetitorEntry",
    "load_monitored_and_competitors",
    "load_latest_snapshot",
    "filter_competitors_for_comparison",
    "should_refresh_competitors_count",
]


class FilteredCompetitorsResult:
    """ Agrupa concorrentes elegíveis para comparação e métricas de filtragem."""

    def __init__(
        self,
        *,
        entries: list["ComparisonCompetitorEntry"],
        filtered_reasons: dict[str, int],
        total_competitors: int,
    ) -> None:
        self.entries = entries
        self.filtered_reasons = filtered_reasons
        self.total_competitors = total_competitors

class ComparisonCompetitorEntry:
    """ Representa um concorrente válido com o preço resolvido para comparação."""

    def __init__(
        self, *, competitor: CompetitorProduct, price: Decimal, price_source: str
    ) -> None:
        self.competitor = competitor
        self.price = price
        self.price_source = price_source

def load_monitored_and_competitors(
    db: Session,
    monitored_id: UUID,
) -> Tuple[Any, List[CompetitorProduct], List[CompetitorProduct], int]:
    """ Carrega monitorado e concorrentes filtrados do banco de dados.

    Realiza dois carregamentos:
    1. Busca o produto monitorado (levanta ValueError se não encontrado)
    2. Carrega todos os concorrentes (incluindo pausados/inativos) e aplica
       a filtragem canônica de elegibilidade

    Args:
        db: Sessão ativa do banco de dados.
        monitored_id: UUID do produto monitorado.

    Returns:
        Tupla de 4 elementos:
            - monitored: Instância do MonitoredProduct
            - available_competitors: Lista de CompetitorProduct elegíveis
            - all_competitors: Lista completa sem filtro (para rebuild de resumo)
            - total_competitors: Contagem total antes da filtragem

    Raises:
        ValueError: Se o monitorado não for encontrado no banco.
    """
    monitored = get_monitored_product_by_id(db, monitored_id)
    if monitored is None:
        raise ValueError(f"Produto monitorado {monitored_id} não encontrado.")

    all_competitors = get_competitors_by_monitored_id(
        db,
        monitored_id,
        include_paused=True,
        include_inactive=True,
    )

    filtered = filter_competitors_for_comparison(db, all_competitors)
    available = [entry.competitor for entry in filtered.entries]
    total = filtered.total_competitors

    filtered_out = total - len(available)
    if filtered_out:
        logger.info(
            "comparison_filtered_competitors",
            monitored_id=str(monitored_id),
            filtered=filtered_out,
            total=total,
            available=len(available),
            reasons=filtered.filtered_reasons,
        )

    return monitored, available, all_competitors, total

def load_latest_snapshot(
    db: Session,
    monitored_id: UUID,
) -> Tuple[Optional[PriceComparisonSummary], Optional[Dict]]:
    """ Carrega o resumo mais recente e extrai seus agregados.

    Args:
        db: Sessão ativa do banco de dados.
        monitored_id: UUID do produto monitorado.

    Returns:
        Tupla de 2 elementos:
            - stored_summary: Objeto ORM PriceComparisonSummary ou None
            - aggregates: Dicionário de agregados ou None se não existir resumo
    """
    stored_summary = get_latest_summary(db, monitored_product_id=monitored_id)
    if stored_summary is None:
        return None, None

    aggregates = stored_summary.aggregates
    if not isinstance(aggregates, dict):
        aggregates = None

    return stored_summary, aggregates

def _resolve_competitor_price(
    db: Session,
    competitor: CompetitorProduct,
) -> Tuple[Optional[Decimal], str]:
    """ Recupera o preço preferencial para comparação com fallback em histórico.

    Estratégia de resolução:
    1. Usa current_price se disponível (fonte preferida)
    2. Consulta o último registro de PriceHistory (fallback para scraping falho)

    Isso reduz falsos negativos em concorrentes com scraping recentemente falho,
    permitindo que o histórico seja usado como referência até a próxima coleta.

    Args:
        db: Sessão ativa do banco de dados.
        competitor: Produto concorrente a ter o preço resolvido.

    Returns:
        Tupla (preço, fonte) onde fonte é "current_price" ou "price_history".
        Retorna (None, "missing") se nenhum preço estiver disponível.
    """
    if competitor.current_price is not None:
        return competitor.current_price, "current_price"

    latest_price = get_latest_price_for_competitor(db, competitor.id)
    return to_decimal(latest_price), "price_history"

def _deduplicate_competitors(
    competitors: List[CompetitorProduct],
) -> List[CompetitorProduct]:
    """ Remove duplicidades mantendo o concorrente mais recente por ID."""
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

def filter_competitors_for_comparison(
    db: Session,
    competitors: List[CompetitorProduct],
) -> FilteredCompetitorsResult:
    """ Filtra concorrentes com a regra canônica de elegibilidade para comparação.

    Esta é a única fonte de verdade para elegibilidade de concorrentes.
    Tanto o fluxo de comparação (run_price_comparison) quanto o de
    recomposição de resumo (rebuild_summary) devem usar esta função.

    Critérios de exclusão (aplicados nesta ordem):
    1. Pausado (is_paused=True)
    2. Status indisponível ou removido
    3. Disponibilidade explicitamente False
    4. Sem preço resolvível (nem current_price nem histórico)

    Para concorrentes com current_price ausente mas histórico disponível,
    o preço histórico é injetado em memória (transiente) para uso no comparador,
    sem alterar o banco de dados.

    Args:
        db: Sessão ativa do banco de dados.
        competitors: Lista de CompetitorProduct a filtrar.

    Returns:
        FilteredCompetitorsResult com entradas elegíveis e métricas de filtragem.
    """
    deduped = _deduplicate_competitors(competitors)
    filtered_reasons: dict[str, int] = {}
    entries: list[ComparisonCompetitorEntry] = []

    for competitor in deduped:
        if getattr(competitor, "is_paused", False):
            filtered_reasons["paused"] = filtered_reasons.get("paused", 0) + 1
            continue

        status_value = getattr(competitor, "status", ProductStatus.available)
        if status_value in {ProductStatus.unavailable, ProductStatus.removed}:
            filtered_reasons["status_unavailable"] = (
                filtered_reasons.get("status_unavailable", 0) + 1
            )
            continue

        if getattr(competitor, "availability", None) is False:
            filtered_reasons["availability_false"] = (
                filtered_reasons.get("availability_false", 0) + 1
            )
            continue

        resolved_price, price_source = _resolve_competitor_price(db, competitor)
        if resolved_price is None:
            filtered_reasons["missing_price"] = (
                filtered_reasons.get("missing_price", 0) + 1
            )
            continue

        if competitor.current_price is None:
            #Preço transitório em memória — não persiste, apenas permite comparação
            competitor.current_price = resolved_price
            competitor._comparison_price_source = price_source  # type: ignore[attr-defined]

        entries.append(
            ComparisonCompetitorEntry(
                competitor=competitor,
                price=resolved_price,
                price_source=price_source,
            )
        )

    return FilteredCompetitorsResult(
        entries=entries,
        filtered_reasons=filtered_reasons,
        total_competitors=len(deduped),
    )

def should_refresh_competitors_count(
    *,
    db: Session,
    monitored_id: UUID,
    summary_timestamp: Any,
) -> bool:
    """ Indica quando a contagem de concorrentes deve ser recalculada.

    Verifica se existe algum concorrente criado APÓS o timestamp do resumo.
    Quando o resumo está desatualizado, a contagem de concorrentes pode
    não refletir novos cadastros feitos desde a última comparação.

    Args:
        db: Sessão ativa do banco de dados.
        monitored_id: UUID do produto monitorado.
        summary_timestamp: Timestamp do resumo persistido. None força refresh.

    Returns:
        True se a contagem está possivelmente desatualizada e deve ser
        recalculada. False se o resumo está atual.
    """
    if summary_timestamp is None:
        #Sem timestamp confiável, evitamos reutilizar contagem possivelmente desatualizada
        return True

    if not hasattr(CompetitorProduct, "created_at"):
        #Fallback defensivo caso o modelo não exponha data de criação
        return True

    latest_created_at = (
        db.query(func.max(CompetitorProduct.created_at))
        .filter(CompetitorProduct.monitored_product_id == monitored_id)
        .scalar()
    )
    if latest_created_at is None:
        return False

    try:
        return latest_created_at > summary_timestamp
    except TypeError:
        #Evita falhas com datas naive/aware — força recálculo seguro
        return True
