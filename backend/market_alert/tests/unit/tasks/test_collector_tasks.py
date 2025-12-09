""" Testes para logs estruturados do coletor. """
from uuid import uuid4

from market_alert.tasks.collector_tasks import _record_outcome


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
        