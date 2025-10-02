import hashlib
import math
import time
from typing import Any, Dict, List

import pytest

class FakeRedis:
    """Simula operações essenciais do Redis para cenários de teste."""

    def __init__(self) -> None:
        """Prepara os armazenamentos internos e o relógio virtual."""
        self._data: Dict[str, object] = {}
        self._expirations: Dict[str, float | None] = {}
        self._scripts: Dict[str, str] = {}
        self._sorted_sets: Dict[str, List[float]] = {}
        self.current_time: float = 0.0

    def _purge_expired(self) -> None:
        """Remove chaves cujo TTL expirou no relógio virtual."""
        expired_keys = [
            key
            for key, expires_at in self._expirations.items()
            if expires_at is not None and expires_at <= self.current_time
        ]
        for key in expired_keys:
            self.delete(key)

    @staticmethod
    def _normalize_score(raw: float | str) -> float:
        """Normaliza os valores de score usados em estruturas ordenadas."""
        if isinstance(raw, str):
            if raw == "-inf":
                return float("-inf")
            if raw in {"+inf", "inf"}:
                return float("inf")
            return float(raw)
        return float(raw)

    def script_load(self, source: str) -> str:
        """Carrega um script fictício e retorna seu hash SHA1 como identificador."""
        sha = hashlib.sha1(source.encode("utf-8")).hexdigest()
        self._scripts[sha] = source
        return sha

    def set(self, key: str, value: object, ex: int | None = None, nx: bool = False) -> bool:
        """ Define um valor e registra opcionalmente o TTL, respeitando a opção NX """
        self._purge_expired()
        if nx and key in self.data:
            return False
        self.data[key] = value
        if ex is not None:
            self._expirations[key] = self.current_time + ex
        else:
            self._expirations.pop(key, None)
        return True

    def setex(self, key: str, ttl: int, value: object) -> None:
        """ Encapsula ``SET`` com expiração obrigatória """
        self.set(key, value, ex=ttl)

    def get(self, key: str) -> object | None:
        """ Obtém o valor associado à chave, respeitando expirações """
        self._purge_expired()
        return self._data.get(key)

    def ttl(self, key: str) -> int:
        """Retorna o TTL restante em segundos, seguindo convenções do Redis."""
        self._purge_expired()
        if key not in self._data:
            return -2
        expires_at = self._expirations.get(key)
        if expires_at is None:
            return -1
        remaining = expires_at - self.current_time
        if remaining <= 0:
            self.delete(key)
            return -2
        return int(math.ceil(remaining))

    def expire(self, key: str, secs: int) -> bool:
        """Atualiza o TTL de uma chave existente."""
        self._purge_expired()
        if key not in self._data:
            return False
        self._expirations[key] = self.current_time + secs
        return True

    def exists(self, key: str) -> int:
        """ Retorna ``1`` qaundo a chave está ativa """
        self._purge_expired()
        return 1 if key in self._data else 0
    
    def incr(self, key: str) -> int:
        """Incrementa e devolve o valor inteiro armazenado na chave."""
        self._purge_expired()
        value = int(self._data.get(key, 0)) + 1
        self._data[key] = value
        return value

    def delete(self, key: str) -> int:
        """Remove chaves de todos os armazenamentos internos."""
        removed = 0
        if key in self._data:
            removed += 1
            self._data.pop(key, None)
        self._expirations.pop(key, None)
        if key in self._sorted_sets:
            removed += 1
            self._sorted_sets.pop(key, None)
        return removed

    def zremrangebyscore(self, key: str, min_score: float | str, max_score: float | str) -> int:
        """Remove elementos do conjunto ordenado dentro do intervalo informado."""
        scores = self._sorted_sets.get(key)
        if scores is None:
            return 0
        min_value = self._normalize_score(min_score)
        max_value = self._normalize_score(max_score)
        original_len = len(scores)
        self._sorted_sets[key] = [
            score for score in scores if not (min_value <= score <= max_value)
        ]
        removed = original_len - len(self._sorted_sets[key])
        if not self._sorted_sets[key]:
            self._sorted_sets.pop(key, None)
        return removed

    def zcard(self, key: str) -> int:
        """Retorna a quantidade de elementos em um conjunto ordenado."""
        scores = self._sorted_sets.get(key, [])
        return len(scores)

    def evalsha(self, sha: str, num_keys: int, *keys_and_args: Any) -> Any:
        """Executa um script previamente carregado com base no hash informado."""
        script = self._scripts.get(sha)
        if script is None:
            raise ValueError("script não encontrado para o SHA informado")
        keys = list(keys_and_args[:num_keys])
        args = list(keys_and_args[num_keys:])
        return self._execute_script(script, keys, args)

    def eval(self, script: str, num_keys: int, *keys_and_args: Any) -> Any:
        """Processa scripts inline necessários nos testes."""
        keys = list(keys_and_args[:num_keys])
        args = list(keys_and_args[num_keys:])
        return self._execute_script(script, keys, args)
    
    def _execute_script(self, script: str, keys: list[str], args: list[Any]) -> Any:
        """Interpreta scripts utilizados pelo cache e pelo rate limiter."""
        if "redis.call('get', KEYS[1]) == ARGV[1]" in script and keys:
            token = args[0] if args else None
            stored = self.get(keys[0])
            if stored == token:
                self.delete(keys[0])
                return 1
            return 0
        if len(keys) == 1 and len(args) == 3:
            redis_key = keys[0]
            now_ms = int(args[0])
            window_ms = int(args[1])
            limit = int(args[2])
            window_start = now_ms - window_ms
            entries = [
                score
                for score in self._sorted_sets.get(redis_key, [])
                if score > window_start
            ]
            entries.append(now_ms)
            self._sorted_sets[redis_key] = entries
            return 1 if len(entries) <= limit else 0
        return None

    def advance_time(self, secs: int) -> None:
        """Avança o relógio interno para facilitar testes de expiração."""
        self.current_time += secs
        self._purge_expired()

@pytest.fixture(autouse=True)
def patch_rate_limiter(monkeypatch):
    """ Substitui a classe Redis por uma fake e evitar conexão real com redis e leitura de arquivo Lua """
    fake_redis = FakeRedis()

    class AsyncFakeRedis:
        """ Adapta o ``FakeRedis`` para a interface assíncrona esperada """
        def __init__(self, backend: FakeRedis) -> None:
            self._backend = backend

        async def get(self, key: str) -> object | None:
            """Replica o comportamento de ``GET`` assíncrono."""
            return self._backend.get(key)
        
        async def setex(self, key: str, ttl: int, value: str) -> None:
            """ Executa ``SETEX`` mantendo a mesma semântica do cliente real """
            self._backend.setex(key, ttl, value)

        async def ttl(self, key: str) -> int:
            """Delega a consulta de TTL preservando códigos de retorno."""
            return self._backend.ttl(key)

        async def delete(self, key: str) -> int:
            """Remove uma chave do armazenamento compartilhado."""
            return self._backend.delete(key)

        async def expire(self, key: str, secs: int) -> bool:
            """Atualiza o TTL da chave informada."""
            return self._backend.expire(key, secs)

        async def set(
            self,
            key: str,
            value: str,
            *,
            ex: int | None = None,
            nx: bool = False,
        ) -> bool:
            """Implementa ``SET`` com suporte a ``NX`` para locks distribuídos."""
            return self._backend.set(key, value, ex=ex, nx=nx)

        async def eval(self, script: str, numkeys: int, *keys_and_args: Any) -> Any:
            """Executa scripts Lua simplificados sobre a instância fake."""
            return self._backend.eval(script, numkeys, *keys_and_args)

        async def evalsha(self, sha: str, numkeys: int, *keys_and_args: Any) -> Any:
            """Encaminha a execução de scripts previamente carregados."""
            return self._backend.evalsha(sha, numkeys, *keys_and_args)

    async_fake = AsyncFakeRedis(fake_redis)

    monkeypatch.setattr("shared.utils.redis_client.get_redis_client", lambda: fake_redis)
    monkeypatch.setattr("market_scraper.utils.rate_limiter.get_redis_client", lambda: fake_redis)
    monkeypatch.setattr("market_scraper.utils.circuit_breaker.get_redis_client", lambda: fake_redis)
    monkeypatch.setattr(
        "market_scraper.utils.cache_adapter.redis.Redis.from_url",
        lambda *a, **k: async_fake,
    )
    monkeypatch.setattr("market_scraper.utils.robots_txt.get_redis_client", lambda: fake_redis)
    monkeypatch.setattr(
        "market_scraper.utils.robots_txt.requests.get",
        lambda *a, **k: type("Resp", (), {"status_code": 200, "text": ""})()
    )

    class DummyCircuitBreaker:
        def allow_request(self, *a, **k):
            return True

        def record_success(self, *a, **k):
            pass

        def record_failure(self, *a, **k):
            pass

    return fake_redis

@pytest.fixture()
def fake_redis(patch_rate_limiter):
    """ Fornece a instância de Redis falso utilizada nos testes """
    return patch_rate_limiter

@pytest.fixture(autouse=True)
def fixed_time(monkeypatch):
    """ Congela o tempo para simulação precisa """
    monkeypatch.setattr(time, "time", lambda: 0.0)
