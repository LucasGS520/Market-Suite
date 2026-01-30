""" Testes para logs estruturados do coletor. """
from uuid import uuid4

from backend.shared.schemas.shared_schemas_products import CompetitorProductCreateScraping
from backend.shared.schemas.shared_schemas_scraper import ScrapeResult
from backend.market_alert.tasks import collector_product_task
from backend.market_alert.tasks.collector_product_task import _record_outcome


class LoggerStub:
    """Logger simplificado para capturar campos estruturados."""

    def __init__(self) -> None:
        self.calls = []

    def info(self, event: str, **kwargs) -> None:
        self.calls.append({"event": event, **kwargs})


def test_record_outcome_inclui_product_id_para_todos_os_casos():
    """Garante que todos os desfechos registram o identificador do produto."""
    logger = LoggerStub()
    monitored_id = uuid4()
    competitor_id = uuid4()
    cenarios = [
        {
            "kind": "monitored",
            "outcome": "new_data",
            "reason": None,
            "monitored_id": monitored_id,
            "competitor_id": None,
        },
        {
            "kind": "monitored",
            "outcome": "no_data",
            "reason": "scraping_suspended",
            "monitored_id": monitored_id,
            "competitor_id": None,
        },
        {
            "kind": "competitor",
            "outcome": "error",
            "reason": "scraper_error",
            "monitored_id": monitored_id,
            "competitor_id": competitor_id,
        },
        {
            "kind": "competitor",
            "outcome": "no_change",
            "reason": "not_modified",
            "monitored_id": monitored_id,
            "competitor_id": competitor_id,
        },
    ]

    for cenario in cenarios:
        _record_outcome(task_logger=logger, **cenario)

    assert len(logger.calls) == len(cenarios)
    for log, cenario in zip(logger.calls, cenarios):
        product_id_esperado = str(cenario["competitor_id"] or cenario["monitored_id"])
        assert log["product_id"] == product_id_esperado
        assert log.get("monitored_id") == (str(cenario["monitored_id"]) if cenario["monitored_id"] else None)
        assert log.get("competitor_id") == (str(cenario["competitor_id"]) if cenario["competitor_id"] else None)

class CounterStub:
    """Contador mínimo para validar incrementos de métricas."""

    def __init__(self) -> None:
        self.labels_calls: list[dict[str, str]] = []
        self.inc_calls = 0

    def labels(self, **kwargs):
        self.labels_calls.append(kwargs)
        return self

    def inc(self) -> None:
        self.inc_calls += 1
        
class CompareTaskStub:
    """Simulador de task Celery para capturar agendamentos."""

    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    def apply_async(self, args=None, queue=None):
        self.calls.append({"args": args, "queue": queue})


def test_run_competitor_scrape_agenda_comparacao_sem_mudanca(monkeypatch):
    """Garante que concorrentes sem mudança ainda agendam comparação do monitorado."""

    compare_stub = CompareTaskStub()
    counter_stub = CounterStub()
    monitored_id = uuid4()

    def fake_scrape_competitor_product(db, user_id, url, payload):
        return ScrapeResult(status="success", product_id="abc")

    payload = CompetitorProductCreateScraping(
        monitored_product_id=monitored_id,
        product_url="http://concorrente",
    )

    monkeypatch.setattr(collector_product_task, "compare_prices_task", compare_stub)
    monkeypatch.setattr(collector_product_task, "COLLECTOR_SUCCESS_NO_CHANGE_TOTAL", counter_stub)
    monkeypatch.setattr(collector_product_task, "scrape_competitor_product", fake_scrape_competitor_product)

    outcome, reason = collector_product_task._run_competitor_scrape(
        db=None,
        task_logger=None,
        monitored_id=monitored_id,
        user_id=uuid4(),
        payload=payload,
    )

    assert outcome == "no_change"
    assert reason == "not_modified"
    assert compare_stub.calls == [{"args": [str(monitored_id)], "queue": "compare"}]
    assert counter_stub.inc_calls == 1
    assert counter_stub.labels_calls == [{"kind": "competitor"}]
