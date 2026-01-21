""" Testes unitários para a task de comparação de preços """

from backend.market_alert.tasks import compare_prices_task


VALID_UUID = "123e4567-e89b-12d3-a456-426655440000"

class DummyTransaction:
    """ Gerencia transações fictícias para simular o begin da sessão """
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

class DummyQuery:
    """ Simula um resultado de query com encadeamento básico """
    def __init__(self, result):
        self._result = result

    def filter(self, *args, **kwargs):
        """ Retorna a própria instância para permitir encadeamento """
        return self

    def first(self):
        """ Retorna o objeto configurado para o teste """
        return self._result

class DummyMonitored:
    """ Representa um monitorado mínimo para interromper o fluxo com segurança """
    def __init__(self, paused: bool):
        self.paused = paused
        self.id = VALID_UUID
        self.user_id = VALID_UUID
        self.product_url = "https://example.com"
        self.availability = None

class DummySession:
    """ Simula uma sessão de banco de dados para uso nos testes """
    def __init__(self, query_result=None):
        self.query_result = query_result
        self.begin_called = False
    
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        self.close()

    def close(self):
        """ Finaliza a sessão fictícia sem efeitos colaterais """

    def begin(self):
        """ Marca o início de uma transação simulada """
        self.begin_called = True
        return DummyTransaction()

    def query(self, *args, **kwargs):
        """ Retorna um query fake para simplificar as buscas """
        return DummyQuery(self.query_result)

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

def build_session_sequence(*sessions):
    """ Fornece sessões em sequência para simular múltiplos contextos """
    iterator = iter(sessions)

    def _session_local():
        return next(iterator)

    return _session_local

def test_compare_prices_task_continues_without_redis(monkeypatch):
    """ Garante que a task siga o fluxo mesmo sem integrações auxiliares """
    def fake_run_price_comparison(*args, **kwargs):
        return {"lowest_competitor": {}, "highest_competitor": {}}

    dummy_logger = DummyLogger()

    monkeypatch.setattr(compare_prices_task, "logger", dummy_logger, raising=False)
    monkeypatch.setattr(
        compare_prices_task,
        "SessionLocal",
        build_session_sequence(
            DummySession(),
            DummySession(query_result=DummyMonitored(paused=False)),
            DummySession(query_result=DummyMonitored(paused=False)),
        ),
        raising=False,
    )
    monkeypatch.setattr(compare_prices_task, "run_price_comparison", fake_run_price_comparison, raising=False)

    compare_prices_task.compare_prices_task.run(VALID_UUID)

    assert dummy_logger.warning_called is False
    
def test_compare_prices_task_skips_when_paused(monkeypatch):
    """Garante que a comparação seja ignorada quando o monitorado está pausado."""
    run_called = False

    def fake_run(*args, **kwargs):
        nonlocal run_called
        run_called = True
        return {"lowest_competitor": {}, "highest_competitor": {}}

    dummy_logger = DummyLogger()

    monkeypatch.setattr(compare_prices_task, "logger", dummy_logger, raising=False)
    monkeypatch.setattr(
        compare_prices_task,
        "SessionLocal",
        build_session_sequence(
            DummySession(query_result=DummyMonitored(paused=True)),
        ),
        raising=False,
    )
    monkeypatch.setattr(compare_prices_task, "run_price_comparison", fake_run, raising=False)

    compare_prices_task.compare_prices_task.run(VALID_UUID)

    assert run_called is False
    assert dummy_logger.warning_called is True
    assert dummy_logger.last_event == "compare_prices_skipped_paused"

def test_compare_prices_task_always_runs(monkeypatch):
    """Executa a comparação mesmo quando chaves duplicadas não são controladas."""

    run_called = False

    def fake_run(*args, **kwargs):
        nonlocal run_called
        run_called = True
        return {"lowest_competitor": {}, "highest_competitor": {}}

    monkeypatch.setattr(compare_prices_task, "logger", DummyLogger(), raising=False)
    monkeypatch.setattr(
        compare_prices_task,
        "SessionLocal",
        build_session_sequence(
            DummySession(query_result=DummyMonitored(paused=False)),
            DummySession(query_result=DummyMonitored(paused=False)),
        ),
        raising=False,
    )
    monkeypatch.setattr(compare_prices_task, "run_price_comparison", fake_run, raising=False)

    compare_prices_task.compare_prices_task.run(VALID_UUID)

    assert run_called is True

def test_compare_prices_task_handles_previous_transaction(monkeypatch):
    """ Garante que a task não falha quando a comparação já iniciou transação """
    first_session = DummySession(query_result=DummyMonitored(paused=False))
    second_session = DummySession(query_result=DummyMonitored(paused=False))

    def fake_run_price_comparison(db, *args, **kwargs):
        with db.begin():
            pass
        return {"lowest_competitor": {}, "highest_competitor": {}}

    monkeypatch.setattr(compare_prices_task, "logger", DummyLogger(), raising=False)
    monkeypatch.setattr(
        compare_prices_task,
        "SessionLocal",
        build_session_sequence(first_session, second_session),
        raising=False,
    )
    monkeypatch.setattr(compare_prices_task, "run_price_comparison", fake_run_price_comparison, raising=False)

    compare_prices_task.compare_prices_task.run(VALID_UUID)

    assert first_session.begin_called is True
    