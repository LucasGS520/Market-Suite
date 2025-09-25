import os
import asyncio
from unittest.mock import AsyncMock

os.environ.setdefault("DATABASE_URL", "sqlite:///test.db")
os.environ.setdefault("SECRET_KEY", "dummy")

from market_scraper.utils_controllers.block_recovery import BlockRecoveryManager, recover_html_if_blocked
from shared.enums import BlockResult


def test_recover_html_if_blocked_encaminha_argumentos(monkeypatch):
    html_simulado = "<html>simulado</html>"
    handle_mock = AsyncMock(return_value=html_simulado)
    monkeypatch.setattr(BlockRecoveryManager, "handle_block", handle_mock)

    resultado = asyncio.run(recover_html_if_blocked("http://example.com", BlockResult.HTTP_403, session_id="sessao"))

    handle_mock.assert_awaited_once_with(BlockResult.HTTP_403, session_id="sessao", url="http://example.com")
    assert resultado == html_simulado
