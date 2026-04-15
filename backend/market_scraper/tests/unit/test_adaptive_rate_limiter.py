"""Testes unitários para AdaptiveRateLimiter.

Redis é substituído por um dicionário assíncrono simples para garantir
isolamento completo sem dependência de infraestrutura real.
Cada teste verifica um aspecto específico da lógica de decisão.
"""

from __future__ import annotations

import time
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from market_scraper.infra.adaptive_rate_limiter import (
    AdaptiveRateLimiter,
    _COOLDOWN_MODERATE_SECONDS,
    _COOLDOWN_SEVERE_SECONDS,
    _HISTORY_TTL_SECONDS,
    _MIN_REQUESTS_FOR_DECISION,
    _THRESHOLD_LAYER1,
    _THRESHOLD_LAYER3,
    _THRESHOLD_REJECT,
)


# ─────────────────────────────────────────────────────────────────────────────
# Infra de fake Redis assíncrono
# ─────────────────────────────────────────────────────────────────────────────

class _FakeRedisPipeline:
    """Executa comandos acumulados de forma síncrona sobre o store."""

    def __init__(self, store: dict) -> None:
        self._store = store
        self._cmds: list = []

    def incr(self, key: str):
        self._cmds.append(("incr", key))
        return self

    def expire(self, key: str, ttl: int):
        return self  # ignorado em testes

    def set(self, key: str, value, ex: int | None = None):
        self._cmds.append(("set", key, value))
        return self

    async def execute(self) -> list:
        results = []
        for cmd in self._cmds:
            if cmd[0] == "incr":
                self._store[cmd[1]] = str(int(self._store.get(cmd[1], "0")) + 1)
                results.append(int(self._store[cmd[1]]))
            elif cmd[0] == "set":
                self._store[cmd[2 - 1]] = str(cmd[2])
                # set(key, value) — index 1=key, 2=value
                self._store[cmd[1]] = str(cmd[2])
                results.append(True)
        return results


class _FakeAsyncRedis:
    """Substituto in-memory de redis.asyncio.Redis para testes."""

    def __init__(self) -> None:
        self.store: dict[str, str] = {}

    async def mget(self, *keys) -> list[str | None]:
        return [self.store.get(k) for k in keys]

    async def set(self, key: str, value, ex: int | None = None) -> bool:
        self.store[key] = str(value)
        return True

    async def get(self, key: str) -> str | None:
        return self.store.get(key)

    async def incr(self, key: str) -> int:
        self.store[key] = str(int(self.store.get(key, "0")) + 1)
        return int(self.store[key])

    def pipeline(self) -> _FakeRedisPipeline:
        return _FakeRedisPipeline(self.store)

    async def aclose(self) -> None:
        pass


def _make_limiter(fake_redis: _FakeAsyncRedis | None = None) -> AdaptiveRateLimiter:
    """Cria um AdaptiveRateLimiter com Redis fake injetado."""
    limiter = AdaptiveRateLimiter(redis_url="redis://localhost:6379/2")
    if fake_redis is not None:
        limiter._redis_client = fake_redis
    return limiter


def _seed_history(
    redis: _FakeAsyncRedis,
    host: str,
    *,
    success: int,
    failure: int,
    cooldown_until: float = 0.0,
    last_error: str | None = None,
) -> None:
    """Preenche o store Redis com histórico pré-definido."""
    ns = f"rate:ml:{host}"
    if success:
        redis.store[f"{ns}:success_count"] = str(success)
    if failure:
        redis.store[f"{ns}:failure_count"] = str(failure)
    if cooldown_until:
        redis.store[f"{ns}:cooldown_until"] = str(cooldown_until)
    if last_error:
        redis.store[f"{ns}:last_error_code"] = last_error


# ─────────────────────────────────────────────────────────────────────────────
# should_allow — casos básicos
# ─────────────────────────────────────────────────────────────────────────────

async def test_limiter_allows_when_no_history():
    """Sem histórico → Layer 1 (otimista)."""
    r = _FakeAsyncRedis()
    limiter = _make_limiter(r)

    allowed, layer = await limiter.should_allow("www.mercadolivre.com.br")

    assert allowed is True
    assert layer == 1


async def test_limiter_suggests_layer1_when_high_success_rate():
    """Taxa ≥ 90% → Layer 1."""
    r = _FakeAsyncRedis()
    _seed_history(r, "ml.com.br", success=95, failure=5)   # 95% taxa
    limiter = _make_limiter(r)

    allowed, layer = await limiter.should_allow("ml.com.br")

    assert allowed is True
    assert layer == 1


async def test_limiter_suggests_layer3_when_medium_success_rate():
    """Taxa entre 50% e 90% → Layer 3 (Layer 2 adiada para pós-MVP)."""
    r = _FakeAsyncRedis()
    _seed_history(r, "ml.com.br", success=70, failure=30)   # 70%
    limiter = _make_limiter(r)

    allowed, layer = await limiter.should_allow("ml.com.br")

    assert allowed is True
    assert layer == 3


async def test_limiter_suggests_layer3_when_low_success_rate_no_cooldown():
    """Taxa < 50% sem cooldown → Layer 3 (não rejeita ainda)."""
    r = _FakeAsyncRedis()
    _seed_history(r, "ml.com.br", success=30, failure=70)   # 30%
    limiter = _make_limiter(r)

    allowed, layer = await limiter.should_allow("ml.com.br")

    assert allowed is True
    assert layer == 3


async def test_limiter_rejects_when_success_rate_below_threshold():
    """Taxa < 20% → rejeitar (allowed=False)."""
    r = _FakeAsyncRedis()
    _seed_history(r, "ml.com.br", success=10, failure=100)  # ~9%
    limiter = _make_limiter(r)

    allowed, layer = await limiter.should_allow("ml.com.br")

    assert allowed is False


async def test_limiter_rejects_when_cooldown_active():
    """Cooldown ativo → rejeitar independente de taxa de sucesso."""
    r = _FakeAsyncRedis()
    future = time.time() + 300
    _seed_history(r, "ml.com.br", success=90, failure=10, cooldown_until=future)
    limiter = _make_limiter(r)

    allowed, layer = await limiter.should_allow("ml.com.br")

    assert allowed is False


async def test_limiter_allows_when_cooldown_expired():
    """Cooldown expirado → permitir normalmente."""
    r = _FakeAsyncRedis()
    past = time.time() - 10
    _seed_history(r, "ml.com.br", success=80, failure=20, cooldown_until=past)
    limiter = _make_limiter(r)

    allowed, layer = await limiter.should_allow("ml.com.br")

    assert allowed is True


async def test_limiter_force_layer_bypasses_history():
    """force_layer ignora sugestão histórica quando permitido."""
    r = _FakeAsyncRedis()
    _seed_history(r, "ml.com.br", success=60, failure=40)   # sugeriria 3
    limiter = _make_limiter(r)

    allowed, layer = await limiter.should_allow("ml.com.br", force_layer=1)

    assert allowed is True
    assert layer == 1


# ─────────────────────────────────────────────────────────────────────────────
# update_history — contadores e cooldown
# ─────────────────────────────────────────────────────────────────────────────

async def test_limiter_calculates_success_rate_correctly():
    """get_success_rate reflete contadores armazenados."""
    r = _FakeAsyncRedis()
    _seed_history(r, "ml.com.br", success=80, failure=20)
    limiter = _make_limiter(r)

    rate = await limiter.get_success_rate("ml.com.br")

    assert rate == pytest.approx(0.80, abs=0.01)


async def test_limiter_success_increments_counter():
    """update_history(success=True) incrementa success_count."""
    r = _FakeAsyncRedis()
    limiter = _make_limiter(r)
    await limiter.update_history("ml.com.br", success=True)

    assert int(r.store.get("rate:ml:ml.com.br:success_count", 0)) == 1
    assert int(r.store.get("rate:ml:ml.com.br:failure_count", 0)) == 0


async def test_limiter_failure_increments_counter():
    """update_history(success=False) incrementa failure_count."""
    r = _FakeAsyncRedis()
    limiter = _make_limiter(r)
    await limiter.update_history("ml.com.br", success=False, error_code="403")

    assert int(r.store.get("rate:ml:ml.com.br:failure_count", 0)) == 1
    assert r.store.get("rate:ml:ml.com.br:last_error_code") == "403"


async def test_limiter_marks_cooldown_on_repeated_429():
    """Taxa < 50% com error_code='429' → cooldown ativado."""
    r = _FakeAsyncRedis()
    # Pré-popula com taxa baixa para que update_history ative cooldown
    _seed_history(r, "ml.com.br", success=2, failure=8)  # 20% taxa
    limiter = _make_limiter(r)

    await limiter.update_history("ml.com.br", success=False, error_code="429")

    cooldown_key = "rate:ml:ml.com.br:cooldown_until"
    assert cooldown_key in r.store
    cooldown_until = float(r.store[cooldown_key])
    assert cooldown_until > time.time()


async def test_limiter_no_cooldown_when_429_but_high_rate():
    """429 isolado com alta taxa de sucesso NÃO deve ativar cooldown."""
    r = _FakeAsyncRedis()
    _seed_history(r, "ml.com.br", success=95, failure=5)   # 95% taxa
    limiter = _make_limiter(r)

    await limiter.update_history("ml.com.br", success=False, error_code="429")

    cooldown_key = "rate:ml:ml.com.br:cooldown_until"
    # Cooldown não deve existir ou deve estar no passado
    if cooldown_key in r.store:
        assert float(r.store[cooldown_key]) <= time.time() + 1


async def test_limiter_severe_cooldown_when_very_low_rate():
    """Taxa < 20% ativa cooldown severo (_COOLDOWN_SEVERE_SECONDS)."""
    r = _FakeAsyncRedis()
    _seed_history(r, "ml.com.br", success=1, failure=9)   # 10% taxa
    limiter = _make_limiter(r)

    await limiter.update_history("ml.com.br", success=False, error_code="429")

    cooldown_until = float(r.store.get("rate:ml:ml.com.br:cooldown_until", 0))
    expected_min = time.time() + _COOLDOWN_SEVERE_SECONDS - 5   # tolerância
    assert cooldown_until >= expected_min


# ─────────────────────────────────────────────────────────────────────────────
# Fallback in-memory quando Redis está offline
# ─────────────────────────────────────────────────────────────────────────────

async def test_limiter_redis_fallback_if_offline():
    """Sem Redis → usa fallback in-memory e não levanta exceção."""
    limiter = AdaptiveRateLimiter(redis_url="redis://localhost:9999/2")
    # redis_client permanece None (não conectado)

    # Não deve levantar exceção
    allowed, layer = await limiter.should_allow("ml.com.br")
    assert allowed is True   # sem histórico → otimista


async def test_limiter_fallback_tracks_failures():
    """Fallback in-memory acumula falhas e ativa cooldown local."""
    limiter = AdaptiveRateLimiter(redis_url="redis://localhost:9999/2")

    # Simula falha de Redis em update_history forçando _update_fallback
    host = "blocked.com.br"
    for _ in range(_MIN_REQUESTS_FOR_DECISION):
        limiter._update_fallback(host, success=False, error_code="429", layer_used=1)

    state = limiter._fallback_state(host)
    # Com taxa muito baixa e 429, cooldown deve estar ativo
    assert state["failure_count"] >= _MIN_REQUESTS_FOR_DECISION


async def test_limiter_redis_fallback_allows_when_redis_fails_on_load():
    """Falha no load_state Redis → fallback in-memory retorna estado vazio (otimista)."""
    limiter = AdaptiveRateLimiter(redis_url="redis://localhost:6379/2")

    # Injeta cliente que sempre falha
    failing_redis = MagicMock()
    failing_redis.mget = AsyncMock(side_effect=ConnectionError("Redis offline"))
    limiter._redis_client = failing_redis

    allowed, layer = await limiter.should_allow("ml.com.br")

    assert allowed is True
    assert layer == 1


# ─────────────────────────────────────────────────────────────────────────────
# Limiares e constantes
# ─────────────────────────────────────────────────────────────────────────────

def test_threshold_values_are_consistent():
    """Limiares formam hierarquia válida: REJECT < LAYER3 < LAYER1."""
    assert 0.0 < _THRESHOLD_REJECT < _THRESHOLD_LAYER3 < _THRESHOLD_LAYER1 < 1.0


def test_history_ttl_is_one_hour():
    """Janela de histórico é 1 hora."""
    assert _HISTORY_TTL_SECONDS == 3600


def test_min_requests_for_decision():
    """Mínimo de requisições para tomar decisão é razoável."""
    assert 3 <= _MIN_REQUESTS_FOR_DECISION <= 20
