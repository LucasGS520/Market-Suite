""" Testes unitários para o resumo de comparações de preço """

from datetime import datetime, timezone

from market_alert.services.services_comparison import build_comparison_summary


class _DummyComparison:
    """ Estrutura simples para simular PriceComparison sem acesso ao banco """

    def __init__(self, data: dict, timestamp: datetime | None = None) -> None:
        self.data = data
        self.timestamp = timestamp or datetime.now(timezone.utc)


def test_build_comparison_summary_without_data() -> None:
    """ Garante que valores nulos são mantidos quando não há comparação salva """

    summary = build_comparison_summary(None, competitors_count=0)

    assert summary["average_competitor_price"] is None
    assert summary["discrepancies"] == []
    assert summary["competitors_count"] == 0


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
            "alerts": [{"type": "price_event"}],
        }
    )

    summary = build_comparison_summary(comparison, competitors_count=2)

    assert summary["average_competitor_price"] == "90.00"
    assert summary["min_competitor_price"] == "80.00"
    assert summary["max_competitor_price"] == "120.00"
    assert summary["position_rank"] == 2
    assert summary["comparison_insights"] == "Preço monitorado acima da média dos concorrentes."
    assert summary["alerts"] == [{"type": "price_event"}]
    