""" Teste unitários para o reenqueue do coletor contínuo """

from datetime import datetime, timedelta, timezone
from uuid import uuid4

from backend.market_alert.enums.enums_products import MonitoringType, MonitoredStatus
from backend.market_alert.models.models_products import MonitoredProduct
from backend.market_alert.tasks import continuous_collector_task


class EnqueueStub:
    """ Simula o enqueue para capturar argumentos """

    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    def __call__(self, monitored_id, next_check_at, source, queue_service):
        self.calls.append(
            {
                "monitored_id": monitored_id,
                "next_check_at": next_check_at,
                "source": source,
                "queue_service": queue_service,
            }
        )
        return True
    
def _build_monitored(next_check_at=None) -> MonitoredProduct:
    """ Cria um monitorado mínimo para testes """
    return MonitoredProduct(
        id=uuid4(),
        user_id=uuid4(),
        name_identification="Produto de teste",
        monitoring_type=MonitoringType.scraping,
        product_url="https://examplo.com/produto",
        normalized_url="https://exemplo.com/produto",
        status=MonitoredStatus.active,
        next_check_at=next_check_at,
    )

def test_requeue_monitored_define_next_check_at_if_missing(monkeypatch):
    """ Garante que o reenqueue usa o horário atual quando não há next_check_at """
    fixed_now = datetime(2024, 1, 1, tzinfo=timezone.utc)
    enqueue_stub = EnqueueStub()

    monkeypatch.setattr(continuous_collector_task, "_utc_now", lambda: fixed_now)
    monkeypatch.setattr(continuous_collector_task, "enqueue_monitored_at", enqueue_stub)

    monitored = _build_monitored(next_check_at=None)

    continuous_collector_task._requeue_monitored(
        monitored=monitored,
        next_check_at=None,
        queue_service=None,
    )

    assert enqueue_stub.calls == [
        {
            "monitored_id": monitored.id,
            "next_check_at": fixed_now,
            "source": "continuous_worker",
            "queue_service": None,
        }
    ]

def test_requeue_monitored_corrects_next_check_at_past_dates(monkeypatch):
    """ Garante que o reenqueue corrige datas no passado para o horário atual """
    fixed_now = datetime(2024, 2, 1, tzinfo=timezone.utc)
    enqueue_stub = EnqueueStub()

    monkeypatch.setattr(continuous_collector_task, "_utc_now", lambda: fixed_now)
    monkeypatch.setattr(continuous_collector_task, "enqueue_monitored_at", enqueue_stub)

    monitored = _build_monitored(next_check_at=fixed_now - timedelta(minutes=10))

    continuous_collector_task._requeue_monitored(
        monitored=monitored,
        next_check_at=None,
        queue_service=None,
    )

    assert enqueue_stub.calls == [
        {
            "monitored_id": monitored.id,
            "next_check_at": fixed_now,
            "source": "continuous_worker",
            "queue_service": None,
        }
    ]