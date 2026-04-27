""" Rate limiter adaptativo com histórico em Redis para o market_scraper.

Rastreia taxa de sucesso por hostname e ajusta automaticamente a
estratégia de aquisição sugerida: tentativa HTTP quando o host coopera
bem, fallback de browser quando detecta bloqueios recorrentes, e
cooldown temporário quando 429s se acumulam.

Schema Redis (namespace ``rate:ml:{hostname}``):

    rate:ml:{host}:success_count    — INCR com TTL 1h
    rate:ml:{host}:failure_count    — INCR com TTL 1h
    rate:ml:{host}:cooldown_until   — timestamp Unix (float), TTL variável
    rate:ml:{host}:last_layer       — estratégia usada na última req (1, 2, 3; nome histórico preservado)
    rate:ml:{host}:last_error_code  — código do último erro ("429", "timeout"…)

Fallback: se Redis estiver indisponível, um dicionário in-memory (não
persistente) garante degradação segura — as decisões são tomadas com base
no estado local do processo.

Uso:

    limiter = adaptive_rate_limiter   # singleton global

    layer, allowed = await limiter.should_allow(host)
    if not allowed:
        raise HTTPException(429, "cooldown ativo")

    html = await fetch_layer(layer, url)
    await limiter.update_history(host, success=True)
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

import structlog

from shared.core.config_base import ConfigBase


logger = structlog.get_logger("adaptive_rate_limiter")

# ────────────────────────────────────────────────────────────────────────────
# Configurações e limiares
# ────────────────────────────────────────────────────────────────────────────

_HISTORY_TTL_SECONDS: int   = 3600          #janela de histórico (1h)
_NAMESPACE: str             = "rate:ml"

#Limiares de taxa de sucesso
_THRESHOLD_HTTP: float    = 0.90          # ≥ 90% → tentativa HTTP
_THRESHOLD_BROWSER: float    = 0.50          # ≥ 50% → browser sob demanda; < 50% → cooldown
_THRESHOLD_REJECT: float    = 0.20          # < 20% → rejeitar completamente

#Durações de cooldown por severidade
_COOLDOWN_MILD_SECONDS: int    = 60         # 50% > rate ≥ 20%, 429 recorrente
_COOLDOWN_MODERATE_SECONDS: int = 300       # < 50%, 429 recorrente
_COOLDOWN_SEVERE_SECONDS: int  = 3600       # < 20%

#Mínimo de requisições para confiar na taxa de sucesso
_MIN_REQUESTS_FOR_DECISION: int = 5


# ────────────────────────────────────────────────────────────────────────────
# Fallback in-memory
# ────────────────────────────────────────────────────────────────────────────

@dataclass
class _HostState:
    """ Estado in-memory por hostname (usado quando Redis está offline)."""
    success_count: int   = 0
    failure_count: int   = 0
    cooldown_until: float = 0.0     #timestamp Unix
    last_layer: int      = 1
    last_error_code: str | None = None


# ────────────────────────────────────────────────────────────────────────────
# Rate limiter principal
# ────────────────────────────────────────────────────────────────────────────

class AdaptiveRateLimiter:
    """ Rastreia taxa de sucesso por host e sugere a estratégia mais adequada.

    Todas as operações são assíncronas. O cliente Redis é criado
    sob demanda e reutilizado por instância. Em caso de falha Redis, o
    fallback in-memory garante que o pipeline continue operando.
    """

    def __init__(
        self,
        *,
        redis_url: str | None = None,
        namespace: str = _NAMESPACE,
        history_ttl: int = _HISTORY_TTL_SECONDS,
    ) -> None:
        self._redis_url = redis_url or self._build_default_url()
        self._namespace = namespace
        self._history_ttl = history_ttl
        self._redis_client: Any = None          # redis.asyncio.Redis (lazy)
        self._fallback: dict[str, _HostState] = {}

    # ── Redis connection (lazy, com fallback) ────────────────────────────

    async def _get_client(self):
        """ Retorna cliente Redis assíncrono (cria se necessário)."""
        if self._redis_client is not None:
            return self._redis_client
        try:
            import redis.asyncio as aioredis
            self._redis_client = aioredis.from_url(
                self._redis_url,
                decode_responses=True,
                socket_timeout=1.0,
                socket_connect_timeout=1.0,
            )
            return self._redis_client
        except Exception as exc:
            logger.warning("adaptive_rate_limiter_redis_init_failed", error=str(exc))
            return None

    async def close(self) -> None:
        """ Fecha a conexão Redis."""
        if self._redis_client is not None:
            try:
                await self._redis_client.aclose()
            except Exception:
                pass
            finally:
                self._redis_client = None

    # ── API pública ──────────────────────────────────────────────────────

    async def should_allow(
        self,
        host: str,
        *,
        force_layer: int | None = None,
    ) -> tuple[bool, int]:
        """ Decide se a requisição deve prosseguir e qual estratégia usar.

        Args:
            host: Hostname alvo (ex: ``"www.mercadolivre.com.br"``).
            force_layer: Quando fornecido, bypassa a decisão histórica e retorna
                         ``(True, force_layer)`` desde que não haja cooldown ativo.

        Returns:
            ``(allowed, layer)`` onde:
            - ``allowed=False`` → cooldown ativo ou taxa de rejeição severa.
            - ``layer`` ∈ {1, 3} — estratégia sugerida quando ``allowed=True``.
        """
        state = await self._load_state(host)

        # ── Cooldown ativo → rejeitar ───────────────────────────────────
        if state["cooldown_until"] > time.time():
            remaining = int(state["cooldown_until"] - time.time())
            logger.info(
                "adaptive_rate_limiter_cooldown_active",
                host=host,
                remaining_seconds=remaining,
            )
            return False, 0

        success, failure = state["success_count"], state["failure_count"]
        total = success + failure

        # ── Sem histórico suficiente → tentativa HTTP otimista ────────────
        if total < _MIN_REQUESTS_FOR_DECISION:
            return True, force_layer or 1

        rate = success / total

        # ── Taxa de rejeição severa → rejeitar ────────────────────────────
        if rate < _THRESHOLD_REJECT:
            logger.warning(
                "adaptive_rate_limiter_reject_low_rate",
                host=host,
                success_rate=round(rate, 3),
                total=total,
            )
            return False, 0

        if force_layer is not None:
            return True, force_layer

        # ── Decisão por taxa de sucesso ──────────────────────────────────
        if rate >= _THRESHOLD_HTTP:
            suggested = 1
        else:
            suggested = 3   #Layer 2 (proxy) adiada para pós-MVP

        logger.debug(
            "adaptive_rate_limiter_decision",
            host=host,
            success_rate=round(rate, 3),
            total_requests=total,
            suggested_layer=suggested,
        )
        return True, suggested

    async def update_history(
        self,
        host: str,
        *,
        success: bool,
        error_code: str | None = None,
        layer_used: int = 1,
    ) -> None:
        """ Registra o resultado de uma requisição no histórico.

        Ativa cooldown automaticamente quando a taxa de sucesso cai abaixo
        do limiar e o erro recorrente é 429 (rate limiting do servidor).

        Args:
            host: Hostname alvo.
            success: ``True`` se o HTML foi obtido com sucesso.
            error_code: Código do erro quando ``success=False``
                        (ex: ``"429"``, ``"timeout"``, ``"403"``).
            layer_used: Estratégia utilizada (1, 2 ou 3).
        """
        try:
            await self._update_redis(host, success=success, error_code=error_code, layer_used=layer_used)
        except Exception as exc:
            logger.warning(
                "adaptive_rate_limiter_redis_update_failed",
                host=host,
                error=str(exc),
            )
            self._update_fallback(host, success=success, error_code=error_code, layer_used=layer_used)

    async def get_success_rate(self, host: str) -> float | None:
        """ Retorna taxa de sucesso atual (0.0–1.0) ou ``None`` se sem dados."""
        state = await self._load_state(host)
        total = state["success_count"] + state["failure_count"]
        if total < 1:
            return None
        return state["success_count"] / total

    # ── Operações Redis ──────────────────────────────────────────────────

    def _key(self, host: str, suffix: str) -> str:
        return f"{self._namespace}:{host}:{suffix}"

    async def _load_state(self, host: str) -> dict[str, Any]:
        """ Carrega estado do Redis; fallback para in-memory se indisponível."""
        client = await self._get_client()
        if client is None:
            return self._fallback_state(host)

        try:
            success_key  = self._key(host, "success_count")
            failure_key  = self._key(host, "failure_count")
            cooldown_key = self._key(host, "cooldown_until")
            layer_key    = self._key(host, "last_layer")
            error_key    = self._key(host, "last_error_code")

            values = await client.mget(
                success_key, failure_key, cooldown_key, layer_key, error_key
            )
            return {
                "success_count":   int(values[0] or 0),
                "failure_count":   int(values[1] or 0),
                "cooldown_until":  float(values[2] or 0.0),
                "last_layer":      int(values[3] or 1),
                "last_error_code": values[4],
            }
        except Exception as exc:
            logger.warning("adaptive_rate_limiter_load_failed", host=host, error=str(exc))
            return self._fallback_state(host)

    async def _update_redis(
        self,
        host: str,
        *,
        success: bool,
        error_code: str | None,
        layer_used: int,
    ) -> None:
        client = await self._get_client()
        if client is None:
            raise ConnectionError("Redis indisponível")

        pipe = client.pipeline()

        if success:
            pipe.incr(self._key(host, "success_count"))
            pipe.expire(self._key(host, "success_count"), self._history_ttl)
        else:
            pipe.incr(self._key(host, "failure_count"))
            pipe.expire(self._key(host, "failure_count"), self._history_ttl)
            if error_code:
                pipe.set(self._key(host, "last_error_code"), error_code, ex=self._history_ttl)

        pipe.set(self._key(host, "last_layer"), layer_used, ex=self._history_ttl)
        await pipe.execute()

        #Re-lê contadores para calcular taxa de sucesso e decidir cooldown
        raw = await client.mget(
            self._key(host, "success_count"),
            self._key(host, "failure_count"),
        )
        s = int(raw[0] or 0)
        f = int(raw[1] or 0)
        total = s + f

        if total >= _MIN_REQUESTS_FOR_DECISION:
            rate = s / total
            await self._maybe_activate_cooldown(
                client, host, rate=rate, error_code=error_code, total=total
            )

        logger.debug(
            "adaptive_rate_limiter_history_updated",
            host=host,
            success=success,
            error_code=error_code,
            layer_used=layer_used,
        )

    async def _maybe_activate_cooldown(
        self,
        client,
        host: str,
        *,
        rate: float,
        error_code: str | None,
        total: int,
    ) -> None:
        """ Ativa cooldown quando a taxa é baixa e o servidor está bloqueando."""
        if rate >= _THRESHOLD_BROWSER:
            return  #taxa OK — sem cooldown

        is_429 = error_code == "429"

        if rate < _THRESHOLD_REJECT:
            cooldown = _COOLDOWN_SEVERE_SECONDS
        elif rate < _THRESHOLD_BROWSER and is_429:
            cooldown = _COOLDOWN_MODERATE_SECONDS
        elif is_429:
            cooldown = _COOLDOWN_MILD_SECONDS
        else:
            return  #taxa baixa mas não por 429 — aguarda mais dados

        until = time.time() + cooldown
        await client.set(
            self._key(host, "cooldown_until"),
            until,
            ex=cooldown + 60,
        )
        logger.warning(
            "adaptive_rate_limiter_cooldown_activated",
            host=host,
            success_rate=round(rate, 3),
            error_code=error_code,
            cooldown_seconds=cooldown,
        )

    # ── Fallback in-memory ───────────────────────────────────────────────

    def _fallback_state(self, host: str) -> dict[str, Any]:
        state = self._fallback.get(host, _HostState())
        return {
            "success_count":   state.success_count,
            "failure_count":   state.failure_count,
            "cooldown_until":  state.cooldown_until,
            "last_layer":      state.last_layer,
            "last_error_code": state.last_error_code,
        }

    def _update_fallback(
        self,
        host: str,
        *,
        success: bool,
        error_code: str | None,
        layer_used: int,
    ) -> None:
        state = self._fallback.setdefault(host, _HostState())
        if success:
            state.success_count += 1
        else:
            state.failure_count += 1
            if error_code:
                state.last_error_code = error_code
        state.last_layer = layer_used

        #Cooldown in-memory (mesma lógica que Redis)
        total = state.success_count + state.failure_count
        if total >= _MIN_REQUESTS_FOR_DECISION:
            rate = state.success_count / total
            is_429 = error_code == "429"
            if rate < _THRESHOLD_REJECT:
                state.cooldown_until = time.time() + _COOLDOWN_SEVERE_SECONDS
            elif rate < _THRESHOLD_BROWSER and is_429:
                state.cooldown_until = time.time() + _COOLDOWN_MODERATE_SECONDS

    @staticmethod
    def _build_default_url() -> str:
        settings = ConfigBase()
        return settings.redis_operational_url


# ───────────────────────────────────────────────────────────────────────────
# Singleton global
# ───────────────────────────────────────────────────────────────────────────

adaptive_rate_limiter = AdaptiveRateLimiter()


__all__ = [
    "AdaptiveRateLimiter",
    "adaptive_rate_limiter",
]
