""" Testes de contrato para desfechos do coletor. """

from uuid import UUID, uuid4

import pytest

from backend.market_alert.tasks import collector_product_task


class DummyCounter:
    """Contador mínimo para rastrear incrementos em métricas."""

    def __init__(self) -> None:
        self.labels_calls: list[dict[str, str]] = []
        self.inc_calls = 0

    def labels(self, **kwargs):
        self.labels_calls.append(kwargs)
        return self

    def inc(self, *_args, **_kwargs) -> None:
        self.inc_calls += 1


class DummyGauge:
    """Gauge simplificado para evitar dependências externas."""

    def __init__(self) -> None:
        self.inc_calls = 0
        self.dec_calls = 0

    def inc(self, *_args, **_kwargs) -> None:
        self.inc_calls += 1

    def dec(self, *_args, **_kwargs) -> None:
        self.dec_calls += 1


class DummySession:
    """Contexto de sessão neutro para evitar acesso ao banco."""

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


@pytest.fixture(autouse=True)
def _patch_metrics(monkeypatch: pytest.MonkeyPatch) -> None:
    """Substitui métricas e locks por dublês simples."""

    error_counter = DummyCounter()
    no_data_counter = DummyCounter()
    success_new_counter = DummyCounter()
    success_no_change_counter = DummyCounter()
    lock_acquired_counter = DummyCounter()
    lock_skipped_counter = DummyCounter()
    in_flight_gauge = DummyGauge()

    monkeypatch.setattr(collector_product_task, "COLLECTOR_ERROR_TOTAL", error_counter)
    monkeypatch.setattr(collector_product_task, "COLLECTOR_NO_DATA_TOTAL", no_data_counter)
    monkeypatch.setattr(collector_product_task, "COLLECTOR_SUCCESS_NEW_DATA_TOTAL", success_new_counter)
    monkeypatch.setattr(collector_product_task, "COLLECTOR_SUCCESS_NO_CHANGE_TOTAL", success_no_change_counter)
    monkeypatch.setattr(collector_product_task, "COLLECTOR_LOCK_ACQUIRED_TOTAL", lock_acquired_counter)
    monkeypatch.setattr(collector_product_task, "COLLECTOR_LOCK_SKIPPED_TOTAL", lock_skipped_counter)
    monkeypatch.setattr(collector_product_task, "SCRAPER_IN_FLIGHT", in_flight_gauge)

    monkeypatch.setattr(collector_product_task, "SessionLocal", lambda: DummySession())


def test_collect_product_mapeia_payload_invalido_para_error(monkeypatch: pytest.MonkeyPatch) -> None:
    """Payload inválido deve ser normalizado para ``error`` mantendo métricas."""

    monkeypatch.setattr(collector_product_task, "is_scraping_suspended", lambda: False)

    outcome, result = collector_product_task.collect_product(None, dispatch_comparison=False)

    assert outcome == "error"
    assert result is None


def test_collect_product_mapeia_suspensao_para_no_result(monkeypatch: pytest.MonkeyPatch) -> None:
    """Suspensão global do scraping retorna ``no_result`` sem aplicar lock."""

    monkeypatch.setattr(collector_product_task, "is_scraping_suspended", lambda: True)

    outcome, result = collector_product_task.collect_product(
        {"monitored_id": str(uuid4()), "url": "http://produto"},
        dispatch_comparison=False,
    )

    assert outcome == "no_result"
    assert result is None


def test_collect_product_mapeia_excecoes_inesperadas(monkeypatch: pytest.MonkeyPatch) -> None:
    """Exceções inesperadas devem ser convertidas em ``error`` e liberar lock."""

    monitored_id = uuid4()

    monkeypatch.setattr(collector_product_task, "is_scraping_suspended", lambda: False)
    monkeypatch.setattr(collector_product_task, "acquire_product_lock", lambda *_a, **_k: True)

    released: list[UUID] = []
    monkeypatch.setattr(collector_product_task, "release_product_lock", lambda target: released.append(target))

    def _boom(*_a, **_k):
        raise RuntimeError("boom")

    monkeypatch.setattr(collector_product_task, "scrape_monitored_product", _boom)

    outcome, result = collector_product_task.collect_product(
        {"monitored_id": str(monitored_id), "url": "http://produto"},
        dispatch_comparison=False,
    )

    assert outcome == "error"
    assert result is None
    assert released == [monitored_id]
    