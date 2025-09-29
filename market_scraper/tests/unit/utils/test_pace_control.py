""" Testes para o ``DomainPaceController`` assegurando controle de ritmo unificado """

import asyncio
from types import SimpleNamespace

import pytest
from fastapi import HTTPException, status

from market_scraper.utils_controllers.pace_control import DomainPaceController
from market_scraper.utils_controllers.configuration.pace_control_config import (
    PaceControlPolicy,
    TokenBucketConfig,
    JitterConfig,
    HumanDelayConfig,
    RateLimitConfig,
)


@pytest.fixture()
def base_policy() -> PaceControlPolicy:
    """ Retorna politica simplificada sem rate limit para testes """
    return PaceControlPolicy(
        rate_limit=None,
        token_bucket=TokenBucketConfig(rate=2.0, capacity=2.0, min_rate=0.5, decrease_factor=0.5),
        jitter=JitterConfig(min=0.0, max=0.0),
        human_delay=HumanDelayConfig(avg_wpm=200.0, base_delay=0.0, fatigue_min=0.0, fatigue_max=0.0),
    )

@pytest.mark.asyncio
async def test_wait_for_turn_consumes_tokens_sem_espera(monkeypatch: pytest.MonkeyPatch, base_policy: PaceControlPolicy) -> None:
    """ Garante que ``wait_for_turn`` consome tokens sem aguardar quando há saldo disponível """
    controller = DomainPaceController("example.com", base_policy)

    called = SimpleNamespace(count=0)

    async def fake_sleep(value: float) -> None:
        called.count += 1
        assert value == 0.0

    monkeypatch.setattr(asyncio, "sleep", fake_sleep)

    await controller.wait_for_turn(circuit_key="example.com", identifier="sessao-1")
    snapshot = controller.snapshot()
    assert snapshot.tokens < snapshot.capacity
    assert called.count == 0

@pytest.mark.asyncio
async def test_wait_for_turn_aplica_sleep_quando_tokens_acabam(monkeypatch: pytest.MonkeyPatch, base_policy: PaceControlPolicy) -> None:
    """ Deve aguardar tempo proporcional quando o bucket fica vazio """
    controller = DomainPaceController("example.com", base_policy)

    sleep_valores: list[float] = []

    async def fake_sleep(value: float) -> None:
        sleep_valores.append(value)

    monkeypatch.setattr(asyncio, "sleep", fake_sleep)

    #Consome tokens existentes rapidamente
    await controller.wait_for_turn(circuit_key="example.com", identifier="sessao-1")
    await controller.wait_for_turn(circuit_key="example.com", identifier="sessao-1")
    await controller.wait_for_turn(circuit_key="example.com", identifier="sessao-1")

    assert any(valor > 0.0 for valor in sleep_valores)

@pytest.mark.asyncio
async def test_backoff_reduz_taxa(monkeypatch: pytest.MonkeyPatch, base_policy: PaceControlPolicy) -> None:
    """ Confere se o backoff reduz a taxa de geração de tokens """
    controller = DomainPaceController("example.com", base_policy)

    async def fake_sleep(value: float) -> None:
        return None
    
    monkeypatch.setattr(asyncio, "sleep", fake_sleep)

    taxa_inicial = controller.snapshot().rate
    await controller.backoff(attempt=2, circuit_key="example.com")
    assert controller.snapshot().rate < taxa_inicial

def test_update_policy_altera_parametros(base_policy: PaceControlPolicy) -> None:
    """ `update_policy` deve aplicar novos parêmetros imediatamente """
    controller = DomainPaceController("example.com", base_policy)
    nova_politica = PaceControlPolicy(
        rate_limit=None,
        token_bucket=TokenBucketConfig(rate=5.0, capacity=5.0, min_rate=1.0, decrease_factor=0.8),
        jitter=JitterConfig(min=0.0, max=0.0),
        human_delay=HumanDelayConfig(avg_wpm=150.0, base_delay=1.0, fatigue_min=0.1, fatigue_max=0.2),
    )

    controller.update_policy(nova_politica)
    snapshot = controller.snapshot()
    assert snapshot.capacity == 5.0
    assert controller.policy == nova_politica

@pytest.mark.asyncio
async def test_wait_for_turn_respeita_rate_limiter(monkeypatch: pytest.MonkeyPatch, base_policy: PaceControlPolicy) -> None:
    """ Deve levantar HTTPException quando o rate limiter negar a requisição """
    policy = PaceControlPolicy(
        rate_limit=RateLimitConfig(max_requests=1, window=60),
        token_bucket=base_policy.token_bucket,
        jitter=base_policy.jitter,
        human_delay=base_policy.human_delay,
    )
    fake_rate_limiter = SimpleNamespace(allow_request=lambda identifier: False)

    monkeypatch.setattr("market_scraper.utils.pace_control.RateLimiter", lambda redis_key, max_requests, window_seconds: fake_rate_limiter)

    controller = DomainPaceController("example.com", policy)

    with pytest.raises(HTTPException) as exc:
        await controller.wait_for_turn(circuit_key="example.com", identifier="sessao-rate")

    assert exc.value.status_code == status.HTTP_429_TOO_MANY_REQUESTS
    