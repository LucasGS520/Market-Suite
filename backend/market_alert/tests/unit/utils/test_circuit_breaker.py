""" Testes unitários para o circuito baseado em Redis. """

from __future__ import annotations

from market_alert.utils import circuit_breaker
from market_alert.utils.circuit_breaker import CircuitBreaker


class FakePipeline:
    """Simula operações de pipeline do Redis para os testes."""

    def __init__(self, client: "FakeRedis") -> None:
        self._client = client
        self._commands: list[tuple] = []

    def incr(self, key: str) -> "FakePipeline":
        self._commands.append(("incr", key))
        return self

    def expire(self, key: str, seconds: int) -> "FakePipeline":
        self._commands.append(("expire", key, seconds))
        return self

    def set(self, key: str, value: str, ex: int | None = None) -> "FakePipeline":
        self._commands.append(("set", key, value, ex))
        return self

    def delete(self, key: str) -> "FakePipeline":
        self._commands.append(("delete", key))
        return self

    def execute(self) -> list[int | bool]:
        """Executa comandos armazenados, espelhando efeitos básicos do Redis."""
        results: list[int | bool] = []
        for command in self._commands:
            action = command[0]
            if action == "incr":
                _, key = command
                value = self._client.storage.get(key, 0) + 1
                self._client.storage[key] = value
                results.append(value)
            elif action == "expire":
                _, key, seconds = command
                self._client.expirations[key] = seconds
                results.append(True)
            elif action == "set":
                _, key, value, ex = command
                self._client.storage[key] = value
                if ex is not None:
                    self._client.expirations[key] = ex
                results.append(True)
            elif action == "delete":
                _, key = command
                exists = key in self._client.storage
                self._client.storage.pop(key, None)
                self._client.expirations.pop(key, None)
                results.append(1 if exists else 0)
        self._commands.clear()
        return results


class FakeRedis:
    """Estrutura simples para reproduzir respostas essenciais do Redis."""

    def __init__(self) -> None:
        self.storage: dict[str, int | str] = {}
        self.expirations: dict[str, int] = {}

    def pipeline(self, _transaction: bool) -> FakePipeline:
        # Criamos uma nova fila de comandos a cada chamada para simular o comportamento real.
        return FakePipeline(self)

    def ttl(self, key: str) -> int:
        return self.expirations.get(key, -1)

    def delete(self, key: str) -> int:
        exists = key in self.storage
        self.storage.pop(key, None)
        self.expirations.pop(key, None)
        return 1 if exists else 0


def test_record_failure_opens_circuit_without_attribute_error() -> None:
    """Garante que o circuito abre sem erros de atributo usando o limiar configurado."""

    fake_client = FakeRedis()
    breaker = CircuitBreaker(
        lambda: fake_client,
        failure_threshold=2,
        failure_window=30,
        cooldown_seconds=60,
    )
    host = "unit.test"

    class _SilentLogger:
        """Ignora avisos para evitar interferência das chaves extras nos testes."""

        def warning(self, *_args, **_kwargs) -> None:
            return None

    original_logger = circuit_breaker.logger
    circuit_breaker.logger = _SilentLogger()

    try:
        breaker.record_failure(host)
        assert breaker.is_open(host) is False

        breaker.record_failure(host)
        assert breaker.is_open(host) is True

        breaker.record_failure(host)
        assert breaker.is_open(host) is True
    finally:
        circuit_breaker.logger = original_logger
        