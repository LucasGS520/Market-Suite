import pytest
import asyncio
from app.utils.block_recovery import BlockRecoveryManager


def test_escalates_suspend_duration(monkeypatch):
    """ Bloqueios consecutivos aumentam o tempo de suspensão """
    calls = []
    monkeypatch.setattr("app.utils.block_recovery.suspend_scraping", lambda d: calls.append(d))
    mgr = BlockRecoveryManager()

    asyncio.run(mgr.handle_block("429", "s1"))
    asyncio.run(mgr.handle_block("429", "s1"))
    asyncio.run(mgr.handle_block("429", "s1"))

    assert calls == [300, 900, 1800]
