import time
import pytest
from unittest.mock import Mock
from fastapi import HTTPException, status
from app.utils.throttle_manager import ThrottleManager

@pytest.fixture()
def fake_sleep(monkeypatch):
    """ Monkeypatch para capturar valores de sleep em vez de realmente aguardar """
    sleeps = []

    def fake(duration):
        sleeps.append(duration)

    monkeypatch.setattr(time, "sleep", fake)
    return sleeps

@pytest.fixture()
def fixed_time(monkeypatch):
    """ Tempo fixo + controle manual do tempo via incremento de contador """
    current = [1000.0]

    def fake_time():
        return current[0]

    def advance(seconds):
        current[0] += seconds

    monkeypatch.setattr(time, "time", fake_time)
    return advance

def test_wait_does_not_sleep_if_tokens_available(fixed_time, fake_sleep):
    """ Testa que wait() não chama sleep se tokens estão disponíveis no Bucket """
    tm = ThrottleManager(rate=2.0, capacity=2)

    tm.wait(circuit_key="t")
    tm.wait(circuit_key="t")

    #Verifica se não houve sleep siginificativo
    sleeps_nonzero = [s for s in fake_sleep if s > 0.01]
    assert sleeps_nonzero == []

    #Consome tudo
    fixed_time(0.1)
    tm.wait(circuit_key="t")
    assert any(s > 0 for s in fake_sleep)

def test_wait_consumes_token_and_triggers_jitter(fixed_time, fake_sleep):
    """ Testa que wait() consome tokens, quando esgota, entra em jitter (sleep com tempo aleatório) """
    tm = ThrottleManager(rate=1.0, capacity=2)

    #Duas chamadas de imediato, consome 2 tokens
    tm.wait(circuit_key="t")
    tm.wait(circuit_key="t")

    #Avança tempo suficiente para recuperar tokens
    fixed_time(0.3)

    #Chamada adicional -> deve aplicar jitter
    tm.wait(circuit_key="t")

    sleeps_nonzero = [s for s in fake_sleep if s > 0.01]
    assert len(sleeps_nonzero) == 1
    assert sleeps_nonzero[0] > 0.01

def test_backoff_reduces_rate_and_calls_circuit_breaker(monkeypatch):
    """ Testa que backoff(attempt) aplica penalidade na taxa, chama record_failure() do CircuitBreaker
    e aplica jitter exponencial """
    #Captura o sleep
    sleeps = []
    monkeypatch.setattr(time, "sleep", lambda sec: sleeps.append(sec))
    monkeypatch.setattr("random.uniform", lambda a, b: 0.5) #Força jitter de 0.5

    #Mock do CircuitBraker
    fake_cb = Mock()
    monkeypatch.setattr("alert_app.utils.throttle_manager.CircuitBreaker", lambda: fake_cb)

    #Cria manager com taxa inicial
    tm = ThrottleManager(rate=2.0, capacity=2)
    rate_before = tm.rate

    #Executa backoff com attempt=2
    tm.backoff(attempt=2, circuit_key="t")

    #Verifica que taxa foi reduzida (penalidade adptativa)
    assert tm.rate < rate_before

    #Verifica que CircuitBraker foi chamado
    fake_cb.record_failure.assert_called_once()

    #Verifica que houve sleep (exponencial)
    assert len(sleeps) == 1
    assert sleeps[0] > 0.0

def test_wait_raises_when_rate_limiter_blocks(monkeypatch):
    """ Espera que wait() lance HTTPException 429 se o rate limiter negar a requisição """
    fake_rate = Mock()
    fake_rate.allow_request.return_value = False
    fake_cb = Mock()

    tm = ThrottleManager(rate=1.0, capacity=1, rate_limiter=fake_rate, circuit_breaker=fake_cb)

    with pytest.raises(HTTPException) as exc:
        tm.wait(identifier="test", circuit_key="cb")

    assert exc.value.status_code == status.HTTP_429_TOO_MANY_REQUESTS
    fake_cb.record_failure.assert_called_once()
