""" Testes unitários para a task de comparação de preços """

from types import SimpleNamespace

from backend.market_alert.tasks import compare_prices_task


VALID_UUID = "123e4567-e89b-12d3-a456-426655440000"

class DummySession:
    """ Simula uma sessão de banco de dados para uso nos testes """
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        self.close()

    def close(self):
        """ Finaliza a sessão fictícia sem efeitos colaterais """

class DummyLogger:
    """ Captura mensagens de log geradas durante a execução da task """
    def __init__(self) -> None:
        self.warning_called = False
        self.last_event = None

    def bind(self, **kwargs):
        return self

    def info(self, *args, **kwargs):
        """ Ignora mensagens informativas durante o teste """

    def warning(self, event, **kwargs):
        """ Registra o último aviso emitido pela task quando houver """
        self.warning_called = True
        self.last_event = event

    def error(self, *args, **kwargs):
        """ Ignora mensagens de erro, pois não são esperadas """

def test_compare_prices_task_continues_without_redis(monkeypatch):
    """ Garante que a task siga o fluxo mesmo sem integrações auxiliares """
    def fake_run_price_comparison(*args, **kwargs):
        return {"lowest_competitor": {}, "highest_competitor": {}}, []

    dummy_logger = DummyLogger()

    monkeypatch.setattr(compare_prices_task, "logger", dummy_logger, raising=False)
    monkeypatch.setattr(compare_prices_task, "SessionLocal", lambda: DummySession(), raising=False)
    monkeypatch.setattr(compare_prices_task, "run_price_comparison", fake_run_price_comparison, raising=False)
    monkeypatch.setattr(
        compare_prices_task,
        "send_notification_task",
        SimpleNamespace(delay=lambda *args, **kwargs: None),
        raising=False,
    )
    monkeypatch.setattr(compare_prices_task, "publish_message", lambda *args, **kwargs: True, raising=False)

    compare_prices_task.compare_prices_task.run(VALID_UUID)

    assert dummy_logger.warning_called is False
    
def test_compare_prices_task_always_runs(monkeypatch):
    """Executa a comparação mesmo quando chaves duplicadas não são controladas."""

    run_called = False

    def fake_run(*args, **kwargs):
        nonlocal run_called
        run_called = True
        return {"lowest_competitor": {}, "highest_competitor": {}}, []

    monkeypatch.setattr(compare_prices_task, "logger", DummyLogger(), raising=False)
    monkeypatch.setattr(compare_prices_task, "SessionLocal", lambda: DummySession(), raising=False)
    monkeypatch.setattr(compare_prices_task, "run_price_comparison", fake_run, raising=False)
    monkeypatch.setattr(
        compare_prices_task,
        "send_notification_task",
        SimpleNamespace(delay=lambda *args, **kwargs: None),
        raising=False,
    )
    monkeypatch.setattr(compare_prices_task, "publish_message", lambda *a, **k: True, raising=False)

    compare_prices_task.compare_prices_task.run(VALID_UUID)

    assert run_called is True

def test_compare_prices_task_publishes_realtime_event(monkeypatch):
    """Garante que o evento seja publicado quando o payload contém identificadores."""

    events: dict[str, dict] = {}

    def fake_run_price_comparison(*args, **kwargs):
        return (
            {
                "monitored_id": VALID_UUID,
                "user_id": VALID_UUID,
                "comparison_id": VALID_UUID,
                "summary": {"teste": True},
                "lowest_competitor": {},
                "highest_competitor": {},
            },
            [],
        )

    def fake_publish(channel, payload):
        events["channel"] = channel
        events["payload"] = payload
        return True

    monkeypatch.setattr(compare_prices_task, "SessionLocal", lambda: DummySession(), raising=False)
    monkeypatch.setattr(compare_prices_task, "run_price_comparison", fake_run_price_comparison, raising=False)
    monkeypatch.setattr(compare_prices_task, "publish_message", fake_publish, raising=False)
    monkeypatch.setattr(
        compare_prices_task,
        "send_notification_task",
        SimpleNamespace(delay=lambda *args, **kwargs: None),
        raising=False,
    )

    compare_prices_task.compare_prices_task.run(VALID_UUID)

    assert events["channel"] == "notifications"
    assert events["payload"]["type"] == "comparison.created"
    assert VALID_UUID in events["payload"]["channels"][0]
    