import time
import pytest
from app.utils.rate_limiter import RateLimiter

def test_allow_request_under_limit():
    """ Verifica que allow request() retorna True quando o numero de chamadas estiver
     abaixo ou igual ao limite definido """
    limiter = RateLimiter(redis_key="rate:teste", max_requests=3, window_seconds=1)

    assert limiter.allow_request() is True
    assert limiter.allow_request() is True
    assert limiter.allow_request() is True

def test_allow_request_exceed_limit():
    """ Simula multiplas chamadas para exceder o limite e confirmar allow_request()
    retorna False após atingir o máximo de requisições permitidas """
    limiter = RateLimiter(redis_key="rate:teste", max_requests=3, window_seconds=1)

    assert limiter.allow_request() is True
    assert limiter.allow_request() is True
    assert limiter.allow_request() is True

    #Chamada já ultrapassou o limite de 3
    assert limiter.allow_request() is False

def test_get_count_removes_old_entries(monkeypatch):
    """ Valida que get_count() remove entradas antigas fora da janela de tempo """
    limiter = RateLimiter(redis_key="rate:teste", max_requests=3, window_seconds=1)

    #Define uma sequência de tempos
    times = [0.0, 0.0, 0.0, 2.0]
    monkeypatch.setattr(time, "time", lambda: times.pop(0))

    #Chamadas em t=0.0 -> todas dentro da janela
    assert limiter.allow_request() is True
    assert limiter.allow_request() is True
    assert limiter.allow_request() is True

    #Agora em t=2.0 -> todos os timestamps anteriores (0 ms) já sairam da janela de 1s
    assert limiter.get_count() == 0

def test_reset_clears_rate_limiter_state():
    """ Testa que reset() apaga completamente a chave do Redis e reinicia a contagem """
    limiter = RateLimiter(redis_key="rate:teste", max_requests=3, window_seconds=1)

    #Três chamadas válidas
    assert limiter.allow_request() is True
    assert limiter.allow_request() is True
    assert limiter.allow_request() is True

    #Reset limpa a chave
    limiter.reset()

    #Com chave limpa, contagem volta ao zero -> novas chamadas aceitas
    assert limiter.allow_request() is True
    assert limiter.get_count() == 1
