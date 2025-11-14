""" Testes unitários para a task de comparação de preços """

from types import SimpleNamespace

from market_alert.tasks import compare_prices_tasks


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
        """ Registra o último aviso emitido pela task """
        self.warning_called = True
        self.last_event = event

    def error(self, *args, **kwargs):
        """ Ignora mensagens de erro, pois não são esperadas """

def test_compare_prices_task_continues_without_redis(monkeypatch):
    """ Garante que a task siga o fluxo mesmo quando o Redis estiver ausente """
    def fake_run_price_comparison(*args, **kwargs):
        return {"lowest_competitor": {}, "highest_competitor": {}}, []

    dummy_logger = DummyLogger()

    monkeypatch.setattr(compare_prices_tasks, "logger", dummy_logger, raising=False)
    monkeypatch.setattr(compare_prices_tasks, "SessionLocal", lambda: DummySession(), raising=False)
    monkeypatch.setattr(compare_prices_tasks, "run_price_comparison", fake_run_price_comparison, raising=False)
    monkeypatch.setattr(
        compare_prices_tasks,
        "send_notification_task",
        SimpleNamespace(delay=lambda *args, **kwargs: None),
        raising=False,
    )
    monkeypatch.setattr(compare_prices_tasks, "redis_client", None, raising=False)
    monkeypatch.setattr(compare_prices_tasks, "get_redis_client", lambda: None, raising=False)
    monkeypatch.setattr(compare_prices_tasks, "register_idempotency_key", lambda **kwargs: None, raising=False)
    monkeypatch.setattr(compare_prices_tasks, "store_idempotency_response", lambda **kwargs: None, raising=False)

    compare_prices_tasks.compare_prices_task.run(VALID_UUID)

    assert dummy_logger.warning_called
    assert dummy_logger.last_event == "compare_prices_redis_unavailable"
    
def test_compare_prices_task_skips_when_idempotent(monkeypatch):
    """Repete execução com mesma chave e garante que nada é reprocessado"""

    class DummyRecord:
        is_new = False
        owner = VALID_UUID
        response = None
        status_code = None

    run_called = False

    def fake_run(*args, **kwargs):
        nonlocal run_called
        run_called = True
        return {}, []

    monkeypatch.setattr(compare_prices_tasks, "logger", DummyLogger(), raising=False)
    monkeypatch.setattr(compare_prices_tasks, "SessionLocal", lambda: DummySession(), raising=False)
    monkeypatch.setattr(compare_prices_tasks, "redis_client", None, raising=False)
    monkeypatch.setattr(compare_prices_tasks, "get_redis_client", lambda: None, raising=False)
    monkeypatch.setattr(compare_prices_tasks, "run_price_comparison", fake_run, raising=False)
    monkeypatch.setattr(
        compare_prices_tasks,
        "register_idempotency_key",
        lambda **kwargs: DummyRecord(),
        raising=False,
    )
    monkeypatch.setattr(compare_prices_tasks, "store_idempotency_response", lambda **kwargs: None, raising=False)
    monkeypatch.setattr(
        compare_prices_tasks,
        "send_notification_task",
        SimpleNamespace(delay=lambda *args, **kwargs: None),
        raising=False,
    )

    compare_prices_tasks.compare_prices_task.run(VALID_UUID, idempotency_key="dup")

    assert run_called is False
    