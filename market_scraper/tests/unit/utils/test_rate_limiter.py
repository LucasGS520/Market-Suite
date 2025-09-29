import time
import os
import importlib
import pytest

from shared.metrics.metrics_scraper import (
    SCRAPER_RATE_LIMIT_LATENCY_SECONDS,
    SCRAPER_RATE_LIMIT_MODE,
    SCRAPER_RATE_LIMIT_REQUESTS_TOTAL,
)

from market_scraper.utils import rate_limiter as rate_limiter_module
from market_scraper.utils.rate_limiter import RateLimiter

def _hist_count(metric, **labels) -> float:
    """ Recupera a contagem registrada em um histograma """
    child = metric.labels(**labels)
    for sample in child._samples():
        if sample.name == "_count":
            return sample.value
    raise AssertionError("Contagem não encontrada para histograma")

def test_allow_request_under_limit():
    """ Verifica que allow request() retorna True quando o numero de chamadas estiver
     abaixo ou igual ao limite definido """
    limiter = RateLimiter(
        redis_key="rate:teste", 
        max_requests=3, 
        window_seconds=1,
        metrics_host="teste",    
    )

    assert limiter.allow_request() is True
    assert limiter.allow_request() is True
    assert limiter.allow_request() is True

def test_allow_request_exceed_limit():
    """ Simula multiplas chamadas para exceder o limite e confirmar allow_request()
    retorna False após atingir o máximo de requisições permitidas """
    limiter = RateLimiter(
        redis_key="rate:teste", 
        max_requests=3, 
        window_seconds=1,
        metrics_host="teste",
    )

    assert limiter.allow_request() is True
    assert limiter.allow_request() is True
    assert limiter.allow_request() is True

    #Chamada já ultrapassou o limite de 3
    assert limiter.allow_request() is False

def test_get_count_removes_old_entries(monkeypatch):
    """ Valida que get_count() remove entradas antigas fora da janela de tempo """
    limiter = RateLimiter(
        redis_key="rate:teste", 
        max_requests=3, 
        window_seconds=1,
        metrics_host="teste",
    )

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
    limiter = RateLimiter(
        redis_key="rate:teste", 
        max_requests=3, 
        window_seconds=1,
        metrics_host="teste",
    )

    #Três chamadas válidas
    assert limiter.allow_request() is True
    assert limiter.allow_request() is True
    assert limiter.allow_request() is True

    #Reset limpa a chave
    limiter.reset()

    #Com chave limpa, contagem volta ao zero -> novas chamadas aceitas
    assert limiter.allow_request() is True
    assert limiter.get_count() == 1

def test_lua_script_path_exists():

    caminho = os.path.join(
        os.path.dirname(rate_limiter_module.__file__),
        os.pardir,
        os.pardir,
        "shared",
        "infra",
        "redis-scripts",
        "sliding_window.lua",
    )

    assert os.path.exists(caminho)

def test_rate_limiter_funciona_sem_redis(monkeypatch):
    rl = importlib.reload(rate_limiter_module)
    monkeypatch.setattr(rl, "get_redis_client", lambda: None)

    carregado = []

    def falso_loader(_):
        carregado.append(True)
        return "sha"

    monkeypatch.setattr(rl, "_load_lua_script", falso_loader)

    limiter = rl.RateLimiter(
        redis_key="rate:teste", 
        max_requests=3, 
        window_seconds=1,
        metrics_host="sem_redis",
    )

    assert carregado == []
    assert limiter.redis is None
    assert limiter.allow_request() is True
    assert limiter.get_count() == 0

    #Não deve gerar erro mesmo sem Redis
    limiter.reset()

    passive_metric = SCRAPER_RATE_LIMIT_REQUESTS_TOTAL.labels(
        host="sem_redis", result="passive"
    )
    assert passive_metric._value.get() >= 1
    assert SCRAPER_RATE_LIMIT_MODE.labels(host="sem_redis")._value.get() == 0

def test_rate_limiter_metricas_incrementam(fake_redis):
    """ Garante que as métricas de allowed e blocked são atualizadas """
    limiter = RateLimiter(
        redis_key="rate:metricas",
        max_requests=2,
        window_seconds=10,
        metrics_host="metricas",
    )

    allowed_counter = SCRAPER_RATE_LIMIT_REQUESTS_TOTAL.labels(
        host="metricas", result="allowed"
    )
    blocked_counter = SCRAPER_RATE_LIMIT_REQUESTS_TOTAL.labels(
        host="metricas", result="blocked"
    )

    allowed_before = allowed_counter._value.get()
    blocked_before = blocked_counter._value.get()
    latency_before = _hist_count(SCRAPER_RATE_LIMIT_LATENCY_SECONDS, host="metricas")

    assert limiter.allow_request() is True
    assert limiter.allow_request() is True
    assert limiter.allow_request() is False

    assert allowed_counter._value.get() == allowed_before + 2
    assert blocked_counter._value.get() == blocked_before + 1
    assert SCRAPER_RATE_LIMIT_MODE.labels(host="metricas")._value.get() == 1
    assert _hist_count(SCRAPER_RATE_LIMIT_LATENCY_SECONDS, host="metricas") >= latency_before + 3
