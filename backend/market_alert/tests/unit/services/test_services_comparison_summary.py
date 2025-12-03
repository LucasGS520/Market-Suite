""" Testes unitários para o resumo de comparações de preço """

from datetime import datetime, timezone
import uuid
from decimal import Decimal

from market_alert.services import services_comparison
from market_alert.services.services_comparison import (
    build_comparison_summary,
    get_comparison_summary_for_user,
)


class _DummyComparison:
    """ Estrutura simples para simular PriceComparison sem acesso ao banco """

    def __init__(self, data: dict, timestamp: datetime | None = None) -> None:
        self.data = data
        self.timestamp = timestamp or datetime.now(timezone.utc)
        self.id = uuid.uuid4()

class _DummySummary:
    """ Estrutura simples para simular PriceComparisonSummary """

    def __init__(
        self,
        aggregates: dict,
        comparison_id: uuid.UUID | None = None,
        timestamp: datetime | None = None,
    ) -> None:
        self.aggregates = aggregates
        self.timestamp = timestamp or datetime.now(timezone.utc)
        self.comparison_id = comparison_id or uuid.uuid4()

def test_get_comparison_summary_for_user_reads_aggregates(monkeypatch) -> None:
    """Usa a contagem persistida no JSON de agregados ao montar o resumo."""

    monitored_id = uuid.uuid4()
    stored = _DummySummary({"competitors_count": 5, "competitors_mean": "50.00"})

    monkeypatch.setattr(
        services_comparison,
        "ensure_user_can_view_monitored",
        lambda **kwargs: None,
    )
    monkeypatch.setattr(
        services_comparison, "get_latest_summary", lambda *_args, **_kwargs: stored
    )
    monkeypatch.setattr(
        services_comparison, "get_comparison_by_id", lambda *_args, **_kwargs: None
    )

    response = get_comparison_summary_for_user(
        db=None, monitored_id=monitored_id, user=object()
    )

    assert response.competitors_count == 5
    assert response.monitored_product_id == monitored_id


def test_get_comparison_summary_for_user_defaults_missing_count(monkeypatch) -> None:
    """Garante fallback seguro quando o snapshot não possui contagem salva."""

    monitored_id = uuid.uuid4()
    stored = _DummySummary({})

    monkeypatch.setattr(
        services_comparison,
        "ensure_user_can_view_monitored",
        lambda **kwargs: None,
    )
    monkeypatch.setattr(
        services_comparison, "get_latest_summary", lambda *_args, **_kwargs: stored
    )
    monkeypatch.setattr(
        services_comparison, "get_comparison_by_id", lambda *_args, **_kwargs: None
    )

    response = get_comparison_summary_for_user(
        db=None, monitored_id=monitored_id, user=object()
    )

    assert response.competitors_count == 0
    assert response.monitored_product_id == monitored_id

def test_build_comparison_summary_without_data() -> None:
    """ Garante que valores nulos são mantidos quando não há comparação salva """

    summary = build_comparison_summary(None, competitors_count=0)

    assert summary["competitors_mean"] is None
    assert summary["discrepancies"] == []
    assert summary["competitors_count"] == 0
    assert summary["competitors_with_price_count"] == 0
    assert summary["competitiveness_status"] is None


def test_build_comparison_summary_with_metrics() -> None:
    """ Valida agregados quando há discrepâncias e alerta disponíveis """

    comparison = _DummyComparison(
        data={
            "monitored_price": "100.00",
            "average_competitor_price": "90.00",
            "lowest_competitor": {"price": "80.00"},
            "highest_competitor": {"price": "120.00"},
            "discrepancies": [
                {"price": "80.00"},
                {"price": "120.00"},
            ],
            "alerts": [{"type": "price_below_monitored"}],
        }
    )

    summary = build_comparison_summary(comparison, competitors_count=2)

    assert summary["competitors_mean"] == Decimal("100.00")
    assert summary["competitors_min"] == Decimal("80.00")
    assert summary["competitors_max"] == Decimal("120.00")
    assert summary["position_rank"] == 2
    assert summary["potential_adjustment"] == Decimal("20.00")
    assert summary["competitors_with_price_count"] == 2
    assert "25.00%" in summary["comparison_insights"]
    assert "R$20.00" in summary["comparison_insights"]
    assert summary["alerts"] == [{"type": "price_below_monitored"}]
    assert summary["competitiveness_status"] == "urgente"

def test_compute_summary_with_multiple_competitors_generates_rank_and_insights() -> None:
    """Gera média, ranking, ajuste e insights quando preços estão disponíveis."""

    comparison = _DummyComparison(
        data={
            "monitored_price": 150,
            "discrepancies": [
                {"price": "80.00"},
                {"price": 120},
            ],
        }
    )

    summary = build_comparison_summary(comparison, competitors_count=2)

    assert summary["competitors_mean"] == Decimal("100.00")
    assert summary["competitors_min"] == Decimal("80.00")
    assert summary["competitors_max"] == Decimal("120.00")
    assert summary["position_rank"] == 3
    assert summary["potential_adjustment"] == Decimal("70.00")
    assert "87.50%" in summary["comparison_insights"]
    assert "R$70.00" in summary["comparison_insights"]


def test_compute_summary_without_competitor_prices_keeps_null_fields() -> None:
    """Mantém campos dependentes de preço nulos quando não há valores de concorrentes."""

    comparison = _DummyComparison(
        data={
            "monitored_price": "120.00",
            "discrepancies": [
                {"price": None},
                {"price": ""},
            ],
        }
    )

    summary = build_comparison_summary(comparison, competitors_count=2)

    assert summary["competitors_with_price_count"] == 0
    assert summary["competitors_mean"] is None
    assert summary["competitors_min"] is None
    assert summary["potential_adjustment"] is None
    assert summary["position_rank"] is None
    assert summary["comparison_insights"] is None
    assert summary["competitiveness_status"] is None
    
def test_build_comparison_summary_with_stored_snapshot() -> None:
    """ Usa resumo persistido quando disponível """

    stored = _DummySummary(
        aggregates={
            "competitors_mean": "95.00",
            "competitors_min": "90.00",
            "competitors_max": "110.00",
            "potential_adjustment": None,
            "competitors_with_price_count": 3,
            "alerts": [],
            "discrepancies": [],
        }
    )

    summary = build_comparison_summary(
        None,
        competitors_count=4,
        stored_summary=stored,
    )

    assert summary["competitors_count"] == 4
    assert summary["competitors_mean"] == Decimal("95.00")
    assert summary["competitors_with_price_count"] == 3
    
def test_build_comparison_summary_preserves_last_comparison_at() -> None:
    """ Garante que o resumo mantém o último horário de comparação original """

    last_comparison_snapshot = "2024-01-01T12:00:00+00:00"
    stored_timestamp = datetime(2024, 1, 2, 12, 0, tzinfo=timezone.utc)
    stored = _DummySummary(
        aggregates={
            "competitors_mean": "95.00",
            "competitors_with_price_count": 2,
            "last_comparison_at": last_comparison_snapshot,
        },
        timestamp=stored_timestamp,
    )

    summary = build_comparison_summary(
        None,
        competitors_count=3,
        stored_summary=stored,
    )

    assert summary["last_comparison_at"] == last_comparison_snapshot
    assert summary["computed_at"] == stored_timestamp
    assert summary["competitors_count"] == 3
    
def test_competitiveness_status_attention_threshold() -> None:
    """Classifica como atenção quando a diferença fica entre 1% e 5%"""

    comparison = _DummyComparison(
        data={
            "monitored_price": "103.00",
            "lowest_competitor": {"price": "100.00"},
            "discrepancies": [{"price": "100.00"}],
        }
    )

    summary = build_comparison_summary(comparison, competitors_count=1)

    assert summary["competitiveness_status"] == "atencao"


def test_competitiveness_status_competitive_when_cheaper() -> None:
    """Mantém status competitivo quando o preço monitorado é igual ou menor"""

    comparison = _DummyComparison(
        data={
            "monitored_price": "95.00",
            "lowest_competitor": {"price": "100.00"},
            "discrepancies": [{"price": "100.00"}],
        }
    )

    summary = build_comparison_summary(comparison, competitors_count=1)

    assert summary["competitiveness_status"] == "competitivo"

def test_competitiveness_status_non_competitive_for_small_positive_delta() -> None:
    """Classifica como não competitivo para diferenças positivas abaixo de 1%"""

    comparison = _DummyComparison(
        data={
            "monitored_price": "100.50",
            "lowest_competitor": {"price": "100.00"},
            "discrepancies": [{"price": "100.00"}],
        }
    )

    summary = build_comparison_summary(comparison, competitors_count=1)

    # Pequenas diferenças agora são consideradas 'atencao'
    assert summary["competitiveness_status"] == "atencao"

def test_competitiveness_status_respects_requested_thresholds() -> None:
    """Valida limites de 0%, 1% e 5% conforme regras solicitadas."""

    cases = [
        ("100.00", "100.00", "competitivo"),
        ("100.10", "100.00", "atencao"),
        ("101.00", "100.00", "atencao"),
        ("101.01", "100.00", "atencao"),
        ("105.00", "100.00", "atencao"),
        ("105.01", "100.00", "urgente"),
    ]

    for monitored_price, reference_price, expected in cases:
        comparison = _DummyComparison(
            data={
                "monitored_price": monitored_price,
                "lowest_competitor": {"price": reference_price},
                "discrepancies": [{"price": reference_price}],
            }
        )

        summary = build_comparison_summary(comparison, competitors_count=1)

        assert summary["competitiveness_status"] == expected


def test_competitiveness_status_none_when_reference_missing_or_invalid() -> None:
    """Evita classificação quando o preço de referência está ausente ou zerado."""

    comparison = _DummyComparison(
        data={
            "monitored_price": "100.00",
            "lowest_competitor": {"price": "0"},
            "discrepancies": [{"price": "0"}],
        }
    )

    summary = build_comparison_summary(comparison, competitors_count=1)

    assert summary["competitiveness_status"] is None


def test_competitiveness_status_uses_lowest_competitor_as_reference() -> None:
    """Garante que apenas o menor preço conhecido seja usado como referência."""

    stored = _DummySummary(
        aggregates={
            "monitored_price": "110.00",
            "competitors_mean": "90.00",
            "competitors_min": None,
        }
    )

    summary = build_comparison_summary(
        None, competitors_count=3, stored_summary=stored
    )

    assert summary["competitiveness_status"] is None


def test_competitiveness_status_small_delta_case() -> None:
    """Reproduz caso real: diferença pequena (centavos) deve ser classificada como atencao."""

    comparison = _DummyComparison(
        data={
            # meu preço maior por R$0.92 sobre o menor concorrente
            "monitored_price": "10348.99",
            "lowest_competitor": {"price": "10348.07"},
            "discrepancies": [{"price": "10348.07"}],
        }
    )

    summary = build_comparison_summary(comparison, competitors_count=2)

    assert summary["competitiveness_status"] == "atencao"
