""" Testes de resiliência para o cliente Redis compartilhado """

from __future__ import annotations

from types import SimpleNamespace

import pytest

import shared.utils.redis_client as redis_client


class _DummyCounter:
    """ Implementação simples de contador para validar incrementos em testes """
    def __init__(self) -> None:
        self.calls = 0

    def inc(self) -> None:
        self.calls += 1

class _DummyGauge:
    """ Gauge minimalista para registrar o último valor definido """
    def __init__(self) -> None:
        self.value: float | None = None

    def set(self, value: float) -> None:
        self.value = value

class _DummyLogger:
    """ Logger simplificado que ignora argumento extra """
    def error (self, *_: object, **__: object) -> None:
        return None
    
@pytest.fixture(autouse=True)
def patch_rate_limiter() -> None:
    """Sobrescreve fixture que injeta Redis Fake em outros testes."""
    yield

@pytest.fixture(autouse=True)
def reset_thread_local(monkeypatch: pytest.MonkeyPatch) -> None:
    """ Garante isolamento substituindo o armazenamento thread-local """
    monkeypatch.setattr(redis_client, "_thread_local", SimpleNamespace())

def test_get_redis_client_retorna_none_em_falha(monkeypatch: pytest.MonkeyPatch) -> None:
    """ Falhas de conexão devem retornar ``None`` a atualizar a métrica de erros """
    metrics_stub = SimpleNamespace(
        REDIS_CONNECTION_ERRORS_TOTAL=_DummyCounter(),
        SCRAPING_SUSPENDED_FLAG=_DummyGauge(),
    )
    monkeypatch.setattr(redis_client, "metrics", metrics_stub)
    monkeypatch.setattr(redis_client, "logger", _DummyLogger())

    def _raise(*_: object, **__: object) -> None:
        raise RuntimeError("erro")
    
    monkeypatch.setattr(
        "shared.utils.redis_client.redis.Redis.from_url",
        _raise,
    )

    client = redis_client.get_redis_client()

    assert client is None
    assert metrics_stub.REDIS_CONNECTION_ERRORS_TOTAL.calls == 1

def test_status_scraping_sem_cliente(monkeypatch: pytest.MonkeyPatch) -> None:
    """ Quando não há Redis disponível deve retornar ``False`` e zerar a flag """
    gauge = _DummyGauge()
    metrics_stub = SimpleNamespace(
        REDIS_CONNECTION_ERRORS_TOTAL=_DummyCounter(),
        SCRAPING_SUSPENDED_FLAG=gauge,
    )
    monkeypatch.setattr(redis_client, "metrics", metrics_stub)
    monkeypatch.setattr(redis_client, "get_redis_client", lambda: None)

    assert redis_client.is_scraping_suspended() is False
    assert gauge.value == 0

    # A retomada deve retornar imediatamente sem tentar tocar no gauge novamente
    redis_client.resume_scraping()

    assert gauge.value == 0
    