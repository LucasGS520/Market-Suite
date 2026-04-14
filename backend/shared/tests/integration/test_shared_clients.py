from __future__ import annotations

import ast
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import httpx
import pytest

from shared.schemas.shared_schemas_orchestrator import WorkflowInput

from .conftest import FakeTemporalClient, FakeWorkflowHandle


pytestmark = pytest.mark.integration


def test_task_dispatcher_sends_canonical_task_to_scraping_queue(monkeypatch):
    import shared.clients.celery.task_dispatcher as module

    calls: list[dict] = []

    class FakeSender:
        def send_task(self, task_name: str, *, kwargs: dict, queue: str):
            calls.append(
                {
                    "task_name": task_name,
                    "kwargs": kwargs,
                    "queue": queue,
                }
            )
            return SimpleNamespace(id="task-123")

    monkeypatch.setattr(module, "_get_sender", lambda: FakeSender())

    task_id = module.send_collection_task({"monitored_id": "abc"})

    assert task_id == "task-123"
    assert calls == [
        {
            "task_name": "market_alert.collectors.tasks.collector_product_task.collect_product_task",
            "kwargs": {"payload": {"monitored_id": "abc"}},
            "queue": "scraping",
        }
    ]


def test_scraper_client_fetch_success_sanitizes_payload_and_keeps_contract(install_scraper_client_runtime):
    module, fake_client, _settings, _rate_limiter, breaker, _redis, _sleeps = install_scraper_client_runtime(
        [
            httpx.Response(
                200,
                json={
                    "name": "Produto",
                    "current_price": "12.34",
                    "source": "example",
                    "payload": {
                        "currency": "BRL",
                        "seller": "Loja A",
                        "internal_debug": "drop-me",
                    },
                },
                headers={"ETag": "abc"},
                request=httpx.Request("POST", "http://scraper.local/scraper/parse"),
            )
        ]
    )

    client = module.ScraperClient()
    result = client.fetch(
        url="https://example.com/product",
        monitored_id="prod-1",
        user_id=uuid4(),
        metadata={"request_id": "req-1"},
        etag="etag-1",
        last_modified=datetime(2025, 1, 1, tzinfo=timezone.utc),
    )

    sent_request = fake_client.requests[0]

    assert result.status_code == 200
    assert result.payload is not None
    assert result.payload.payload == {"currency": "BRL", "seller": "Loja A"}
    assert sent_request["path"] == "/scraper/parse"
    assert sent_request["headers"]["If-None-Match"] == "etag-1"
    assert sent_request["headers"]["X-Service-Token"] == "secret-token"
    assert sent_request["json"]["metadata"]["monitored_id"] == "prod-1"
    assert sent_request["json"]["metadata"]["request_id"] == "req-1"
    assert breaker.successes == ["example.com"]
    assert fake_client.closed is False

    client.close()
    assert fake_client.closed is True


def test_scraper_client_retries_transient_429_deterministically(install_scraper_client_runtime):
    retry_at = datetime.now(timezone.utc) + timedelta(seconds=4)
    module, _fake_client, _settings, _rate_limiter, breaker, redis_client, sleeps = install_scraper_client_runtime(
        [
            httpx.Response(
                429,
                headers={"Retry-After": retry_at.strftime("%a, %d %b %Y %H:%M:%S GMT")},
                request=httpx.Request("POST", "http://scraper.local/scraper/parse"),
            ),
            httpx.Response(
                200,
                json={"name": "Produto", "source": "example"},
                request=httpx.Request("POST", "http://scraper.local/scraper/parse"),
            ),
        ]
    )

    result = module.ScraperClient().fetch(url="https://example.com/product")

    assert result.status_code == 200
    assert result.payload is not None
    assert result.payload.name == "Produto"
    assert breaker.failures == ["example.com"]
    assert breaker.successes == ["example.com"]
    assert len(sleeps) == 1
    assert sleeps[0] >= 0
    assert redis_client.values["scraper:host-retry:example.com"] == 1


def test_scraper_client_handles_timeout_and_parse_error_without_transport_leak(install_scraper_client_runtime):
    module, _fake_client, _settings, _rate_limiter, breaker, _redis, sleeps = install_scraper_client_runtime(
        [
            httpx.TimeoutException(
                "slow upstream",
                request=httpx.Request("POST", "http://scraper.local/scraper/parse"),
            ),
            httpx.TimeoutException(
                "slow upstream",
                request=httpx.Request("POST", "http://scraper.local/scraper/parse"),
            ),
        ]
    )

    with pytest.raises(module.ScraperClientError, match="Tempo limite"):
        module.ScraperClient().fetch(url="https://example.com/product")

    assert breaker.failures == ["example.com", "example.com"]
    assert len(sleeps) == 1


def test_scraper_client_parse_raises_domain_error_for_422(install_scraper_client_runtime):
    module, _fake_client, _settings, _rate_limiter, breaker, _redis, _sleeps = install_scraper_client_runtime(
        [
            httpx.Response(
                422,
                json={"error_code": "invalid_product_url"},
                request=httpx.Request("POST", "http://scraper.local/scraper/parse"),
            )
        ]
    )

    with pytest.raises(module.ScraperClientError, match="invalid_product_url"):
        module.ScraperClient().parse(url="https://example.com/product")

    assert breaker.successes == ["example.com"]


async def test_temporal_client_retries_connect_and_signal_with_start(install_temporal_runtime):
    from shared.clients.temporal.orchestrator_client import _WORKFLOW_ID_REUSE

    handle = FakeWorkflowHandle()
    fake_temporal = FakeTemporalClient(start_handle=handle)
    module, _rpc_error, sleeps, connect_calls = install_temporal_runtime(
        [RuntimeError("down"), fake_temporal]
    )
    client = module.TemporalOrchestrationClient()

    result = await client.signal_with_start(
        WorkflowInput(monitored_id="mon-1", user_id="user-1"),
        signal_name="resume",
        signal_arg={"force": True},
    )

    assert result is True
    assert sleeps == [1]
    assert connect_calls == [
        ("localhost:7233", "default"),
        ("localhost:7233", "default"),
    ]
    assert fake_temporal.started == [
        {
            "workflow_name": "MonitoredProductWorkflow",
            "workflow_input": WorkflowInput(monitored_id="mon-1", user_id="user-1"),
            "id": "monitored:mon-1",
            "task_queue": "market-orchestrator-test",
            "id_reuse_policy": _WORKFLOW_ID_REUSE,
        }
    ]
    assert handle.signal_calls == [("resume", {"force": True})]


async def test_temporal_client_query_converts_snapshot_dict(install_temporal_runtime):
    from market_orchestrator.enums.enums_workflow import WorkflowState
    from market_orchestrator.schemas.schemas_snapshot import WorkflowSnapshot

    handle = FakeWorkflowHandle(
        query_response={
            "state": "Paused",
            "next_run_at": "2025-01-02T10:00:00",
            "last_run_at": "2025-01-01T10:00:00",
            "last_error": "none",
            "attempt_count": 2,
            "monitored_id": "mon-2",
        }
    )
    fake_temporal = FakeTemporalClient(handles={"monitored:mon-2": handle})
    module, _rpc_error, _sleeps, _connect_calls = install_temporal_runtime([fake_temporal])
    client = module.TemporalOrchestrationClient()

    snapshot = await client.query("mon-2")

    assert isinstance(snapshot, WorkflowSnapshot)
    assert snapshot.state == WorkflowState.Paused
    assert snapshot.monitored_id == "mon-2"
    assert snapshot.attempt_count == 2
    assert snapshot.next_run_at == datetime(2025, 1, 2, 10, 0)
    assert handle.query_calls == ["get_state"]


async def test_temporal_client_handles_workflow_not_found_and_connectivity_probe_fallback(
    install_temporal_runtime,
):
    handle = FakeWorkflowHandle()
    fake_temporal = FakeTemporalClient(handles={"monitored:mon-3": handle})
    module, fake_rpc_error, _sleeps, _connect_calls = install_temporal_runtime([fake_temporal])
    handle.signal_error = fake_rpc_error("workflow not found")
    client = module.TemporalOrchestrationClient()

    assert await client.signal("pause", "mon-3") is False

    module, _fake_rpc_error, _probe_sleeps, probe_connect_calls = install_temporal_runtime(
        [RuntimeError("down")]
    )
    probe_client = module.TemporalOrchestrationClient()

    assert await probe_client.probe_connectivity() is False
    assert probe_connect_calls == [("localhost:7233", "default")]


def test_shared_architecture_service_import_boundaries_are_explicit():
    shared_dir = Path(__file__).resolve().parents[2]
    allowed_imports = {
        "clients/scraper/scraper_client.py": {"market_alert"},
        "clients/temporal/orchestrator_client.py": {"market_orchestrator"},
    }
    violations: list[str] = []

    for file_path in shared_dir.rglob("*.py"):
        if "tests" in file_path.parts:
            continue
        relative_path = file_path.relative_to(shared_dir).as_posix()
        tree = ast.parse(file_path.read_text(encoding="utf-8"), filename=str(file_path))

        imported_services: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported_services.update(
                    alias.name.split(".")[0]
                    for alias in node.names
                    if alias.name.split(".")[0] in {"market_alert", "market_orchestrator", "market_scraper"}
                )
            elif isinstance(node, ast.ImportFrom) and node.module:
                root = node.module.split(".")[0]
                if root in {"market_alert", "market_orchestrator", "market_scraper"}:
                    imported_services.add(root)

        unexpected = imported_services - allowed_imports.get(relative_path, set())
        if unexpected:
            violations.append(f"{relative_path}: {sorted(unexpected)}")

    assert violations == []
