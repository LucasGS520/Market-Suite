""" Testes unitários para proteção de burst de dispatch de coleta.

Cobre _check_dispatch_burst e supressão em enqueue_collect.
"""
from __future__ import annotations

from uuid import uuid4

import pytest

import market_alert.collectors.dispatch.collection_enqueue as enqueue_module
import market_alert.core.config_alert as config_module


pytestmark = pytest.mark.unit


# ---------------------------------------------------------------------------
# _check_dispatch_burst
# ---------------------------------------------------------------------------

def test_check_dispatch_burst_allows_when_cooldown_disabled(monkeypatch) -> None:
    """Quando cooldown=0, nunca suprime — sem consulta Redis."""
    monkeypatch.setattr(config_module.settings, "COLLECTION_DISPATCH_COOLDOWN_SECONDS", 0)

    result = enqueue_module._check_dispatch_burst(str(uuid4()))

    assert result is True


def test_check_dispatch_burst_allows_first_dispatch(monkeypatch) -> None:
    """Primeiro dispatch na janela: set_key_with_ttl retorna True → permite."""
    monkeypatch.setattr(config_module.settings, "COLLECTION_DISPATCH_COOLDOWN_SECONDS", 30)
    monkeypatch.setattr(enqueue_module, "set_key_with_ttl", lambda key, val, ttl, only_if_absent: True)

    result = enqueue_module._check_dispatch_burst(str(uuid4()))

    assert result is True


def test_check_dispatch_burst_suppresses_second_dispatch(monkeypatch) -> None:
    """Segundo dispatch na mesma janela: set_key_with_ttl retorna False → suprime."""
    monkeypatch.setattr(config_module.settings, "COLLECTION_DISPATCH_COOLDOWN_SECONDS", 30)
    monkeypatch.setattr(enqueue_module, "set_key_with_ttl", lambda key, val, ttl, only_if_absent: False)

    result = enqueue_module._check_dispatch_burst(str(uuid4()))

    assert result is False


def test_check_dispatch_burst_fails_open_when_redis_unavailable(monkeypatch) -> None:
    """Redis indisponível (retorna None) → fail-open, permite dispatch."""
    monkeypatch.setattr(config_module.settings, "COLLECTION_DISPATCH_COOLDOWN_SECONDS", 30)
    monkeypatch.setattr(enqueue_module, "set_key_with_ttl", lambda key, val, ttl, only_if_absent: None)

    result = enqueue_module._check_dispatch_burst(str(uuid4()))

    assert result is True


# ---------------------------------------------------------------------------
# enqueue_collect — supressão por burst
# ---------------------------------------------------------------------------

def test_enqueue_collect_suppresses_when_burst_detected(monkeypatch) -> None:
    """Quando _check_dispatch_burst retorna False, enqueuer._send NÃO é chamado."""
    from shared.schemas.shared_schemas_orchestrator import CollectionPayload

    product_id = uuid4()
    payload = CollectionPayload(
        version=1,
        kind="monitored",
        monitored_id=str(product_id),
        url="https://example.com/produto",
        trace_id=str(uuid4()),
        user_id=str(uuid4()),
        name="Produto",
    )

    send_calls: list = []

    class _FakeEnqueuer:
        def _send(self, p, *, countdown=None):
            send_calls.append(p)

    monkeypatch.setattr(enqueue_module, "_check_dispatch_burst", lambda pid: False)
    monkeypatch.setattr(enqueue_module, "_get_enqueuer", lambda: _FakeEnqueuer())
    monkeypatch.setattr(config_module.settings, "COLLECTION_DISPATCH_COOLDOWN_SECONDS", 30)

    enqueue_module.enqueue_collect(payload)

    assert send_calls == [], "enqueuer._send não deve ser chamado quando burst está ativo"


def test_enqueue_collect_forwards_when_burst_clear(monkeypatch) -> None:
    """Quando _check_dispatch_burst retorna True, enqueuer._send é chamado."""
    from shared.schemas.shared_schemas_orchestrator import CollectionPayload

    product_id = uuid4()
    payload = CollectionPayload(
        version=1,
        kind="monitored",
        monitored_id=str(product_id),
        url="https://example.com/produto",
        trace_id=str(uuid4()),
        user_id=str(uuid4()),
        name="Produto",
    )

    send_calls: list = []

    class _FakeEnqueuer:
        def _send(self, p, *, countdown=None):
            send_calls.append(p)

    monkeypatch.setattr(enqueue_module, "_check_dispatch_burst", lambda pid: True)
    monkeypatch.setattr(enqueue_module, "_get_enqueuer", lambda: _FakeEnqueuer())

    enqueue_module.enqueue_collect(payload)

    assert len(send_calls) == 1
