"""Fixtures auxiliares utilizados nos testes do ``market_scraper``"""

from __future__ import annotations

import pytest


@pytest.fixture
def monkeypath(monkeypatch: pytest.MonkeyPatch) -> pytest.MonkeyPatch:
    """Fornece alias em português para o fixture ``monkeypatch`` do Pytest"""
    #Mantemos este alias para cobrir testes legados que ainda utilizam o nome incorreto
    return monkeypatch
