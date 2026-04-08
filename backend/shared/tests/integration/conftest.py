from __future__ import annotations

from dataclasses import dataclass, field
from fnmatch import fnmatch
from types import SimpleNamespace
from typing import Any

import httpx
import pytest


class FakePipeline:
    def __init__(self, redis: "FakeRedis") -> None:
        self.redis = redis
        self.operations: list[tuple[str, tuple[Any, ...], dict[str, Any]]] = []

    def incr(self, key: str):
        self.operations.append(("incr", (key,), {}))
        return self

    def expire(self, key: str, seconds: int):
        self.operations.append(("expire", (key, seconds), {}))
        return self

    def execute(self):
        results = []
        for operation, args, kwargs in self.operations:
            results.append(getattr(self.redis, operation)(*args, **kwargs))
        self.operations.clear()
        return results


class FakeRedis:
    def __init__(self) -> None:
        self.values: dict[str, Any] = {}
        self.expirations: dict[str, int] = {}

    def incr(self, key: str) -> int:
        current = int(self.values.get(key, 0)) + 1
        self.values[key] = current
        return current

    def expire(self, key: str, seconds: int) -> bool:
        self.expirations[key] = seconds
        return True

    def pipeline(self, _transaction: bool) -> FakePipeline:
        return FakePipeline(self)

    def delete(self, *keys: str) -> int:
        deleted = 0
        for key in keys:
            if key in self.values:
                deleted += 1
                self.values.pop(key, None)
        return deleted

    def scan(self, cursor: int, match: str, count: int = 100):
        if cursor != 0:
            return 0, []
        return 0, [key for key in self.values if fnmatch(key, match)][:count]


@dataclass
class FakeRateLimiter:
    decisions: list[bool] = field(default_factory=list)
    calls: list[str] = field(default_factory=list)

    def allow(self, host: str) -> bool:
        self.calls.append(host)
        if self.decisions:
            return self.decisions.pop(0)
        return True


@dataclass
class FakeCircuitBreaker:
    open_hosts: set[str] = field(default_factory=set)
    failures: list[str] = field(default_factory=list)
    successes: list[str] = field(default_factory=list)

    def is_open(self, host: str) -> bool:
        return host in self.open_hosts

    def record_failure(self, host: str) -> None:
        self.failures.append(host)

    def record_success(self, host: str) -> None:
        self.successes.append(host)


class SequencedSyncClient:
    def __init__(self, sequence: list[Any]) -> None:
        self.sequence = list(sequence)
        self.requests: list[dict[str, Any]] = []
        self.closed = False

    def post(self, path: str, *, json: dict[str, Any] | None = None, headers: dict[str, str] | None = None):
        self.requests.append(
            {
                "path": path,
                "json": json,
                "headers": headers,
            }
        )
        current = self.sequence.pop(0)
        if isinstance(current, BaseException):
            raise current
        return current

    def close(self) -> None:
        self.closed = True


@dataclass
class FakeWorkflowHandle:
    query_response: Any = None
    signal_error: Exception | None = None
    signal_calls: list[tuple[Any, ...]] = field(default_factory=list)
    query_calls: list[str] = field(default_factory=list)

    async def signal(self, signal_name: str, payload: Any = ...):
        if self.signal_error is not None:
            raise self.signal_error
        if payload is ...:
            self.signal_calls.append((signal_name,))
        else:
            self.signal_calls.append((signal_name, payload))

    async def query(self, query_name: str):
        self.query_calls.append(query_name)
        if isinstance(self.query_response, BaseException):
            raise self.query_response
        return self.query_response


@dataclass
class FakeTemporalClient:
    start_handle: FakeWorkflowHandle = field(default_factory=FakeWorkflowHandle)
    handles: dict[str, FakeWorkflowHandle] = field(default_factory=dict)
    started: list[dict[str, Any]] = field(default_factory=list)
    requested_workflows: list[str] = field(default_factory=list)

    async def start_workflow(
        self,
        workflow_name: str,
        workflow_input: Any,
        *,
        id: str,
        task_queue: str,
        id_reuse_policy: Any,
    ) -> FakeWorkflowHandle:
        self.started.append(
            {
                "workflow_name": workflow_name,
                "workflow_input": workflow_input,
                "id": id,
                "task_queue": task_queue,
                "id_reuse_policy": id_reuse_policy,
            }
        )
        self.handles.setdefault(id, self.start_handle)
        return self.start_handle

    def get_workflow_handle(self, workflow_id: str) -> FakeWorkflowHandle:
        self.requested_workflows.append(workflow_id)
        return self.handles[workflow_id]


@pytest.fixture
def install_scraper_client_runtime(monkeypatch):
    import shared.clients.scraper.scraper_client as module

    settings = SimpleNamespace(
        SCRAPER_SERVICE_URL="http://scraper.local",
        HTTP_USER_AGENT="pytest-agent",
        SCRAPER_CONNECT_TIMEOUT=0.1,
        SCRAPER_READ_TIMEOUT=0.1,
        SCRAPER_TOTAL_TIMEOUT=0.2,
        SCRAPER_HTTP_MAX_CONNECTIONS=4,
        SCRAPER_HTTP_MAX_KEEPALIVE=2,
        SCRAPER_HTTP_KEEPALIVE_EXPIRY=1.0,
        SCRAPER_SERVICE_AUTH_HEADER="X-Service-Token",
        SCRAPER_SERVICE_AUTH_TOKEN="secret-token",
        SCRAPER_RETRY_ATTEMPTS=2,
        SCRAPER_RETRY_BACKOFF_MIN=0.5,
        SCRAPER_RETRY_BACKOFF_MAX=2.0,
        SCRAPER_HOST_RETRY_WINDOW_SECONDS=30,
        SCRAPER_HOST_RETRY_MAX_ATTEMPTS=3,
    )
    rate_limiter = FakeRateLimiter()
    circuit_breaker = FakeCircuitBreaker()
    retry_window_redis = FakeRedis()
    sleeps: list[float] = []

    monkeypatch.setattr(module, "_scraper_settings", lambda: settings)
    monkeypatch.setattr(module, "_rate_limiter", lambda: rate_limiter)
    monkeypatch.setattr(module, "_circuit_breaker", lambda: circuit_breaker)
    monkeypatch.setattr(module, "get_redis_operational", lambda: retry_window_redis)
    monkeypatch.setattr(module.time, "sleep", lambda delay: sleeps.append(delay))
    monkeypatch.setattr(module.random, "uniform", lambda _a, _b: 0.0)

    def _install(sequence: list[Any]):
        fake_client = SequencedSyncClient(sequence)
        monkeypatch.setattr(module, "_build_sync_client", lambda base_url, headers: fake_client)
        return module, fake_client, settings, rate_limiter, circuit_breaker, retry_window_redis, sleeps

    return _install


@pytest.fixture
def install_temporal_runtime(monkeypatch):
    import shared.clients.temporal.orchestrator_client as module

    class FakeRPCError(Exception):
        pass

    def _install(sequence: list[Any], *, task_queue: str = "market-orchestrator-test"):
        sleeps: list[int] = []
        connect_calls: list[tuple[str, str]] = []
        config = SimpleNamespace(
            TEMPORAL_NAMESPACE="default",
            TEMPORAL_TASK_QUEUE=task_queue,
            temporal_target="localhost:7233",
        )

        async def fake_sleep(delay: int) -> None:
            sleeps.append(delay)

        async def fake_connect(target: str, *, namespace: str):
            connect_calls.append((target, namespace))
            current = sequence.pop(0)
            if isinstance(current, BaseException):
                raise current
            return current

        monkeypatch.setattr(module, "RPCError", FakeRPCError)
        monkeypatch.setattr(module.asyncio, "sleep", fake_sleep)
        monkeypatch.setattr(module, "_config", lambda: config)
        monkeypatch.setattr(module.Client, "connect", fake_connect)
        return module, FakeRPCError, sleeps, connect_calls

    return _install
