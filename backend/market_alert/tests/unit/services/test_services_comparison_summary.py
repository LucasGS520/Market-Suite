""" Testes unitários para o resumo de comparações de preço """

from datetime import datetime, timezone
import uuid
from decimal import Decimal

from market_alert.services.services_comparison import build_comparison_summary


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

    assert summary["competitors_mean"] == Decimal("90.00")
    assert summary["competitors_min"] == Decimal("80.00")
    assert summary["competitors_max"] == Decimal("120.00")
    assert summary["position_rank"] == 2
    assert summary["potential_adjustment"] == Decimal("20.00")
    assert summary["competitors_with_price_count"] == 2
    assert summary["comparison_insights"] == "Preço monitorado acima da média dos concorrentes."
    assert summary["alerts"] == [{"type": "price_below_monitored"}]
    assert summary["competitiveness_status"] == "urgente"
    
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
    """Classifica como atenção quando a diferença fica entre 3% e 10%"""

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

def test_competitiveness_status_competitive_for_small_positive_delta() -> None:
    """Mantém status competitivo para diferenças pequenas e positivas"""

    comparison = _DummyComparison(
        data={
            "monitored_price": "100.50",
            "lowest_competitor": {"price": "100.00"},
            "discrepancies": [{"price": "100.00"}],
        }
    )

    summary = build_comparison_summary(comparison, competitors_count=1)

    assert summary["competitiveness_status"] == "competitivo"
