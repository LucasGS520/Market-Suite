import asyncio
from unittest.mock import Mock

import pytest
import httpx

from market_scraper.utils.block_recovery import BlockRecoveryManager
from shared.enums import BlockResult


def _setup_managers():
    ua = Mock()
    ua.get_user_agent.return_value = "UA"
    cookie = Mock()
    cookie.get_cookies.return_value = {}
    delay = Mock()
    mgr = BlockRecoveryManager(ua_manager=ua, cookie_manager=cookie, delay_manager=delay)
    return mgr, ua, cookie, delay

def test_handle_block_rotaciona_ua(monkeypatch):
    mgr, ua, cookie, delay = _setup_managers()
    monkeypatch.setattr("shared.utils.redis_client.suspend_scraping", lambda s: None)

    class DummyClient:
        def __init__(self, *a, **k):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def get(self, url):
            class Resp:
                status_code = 200
                text = "<html>ok</html>"
                cookies = {}

                def raises_for_status(self):
                    return None

            return Resp()

    monkeypatch.setattr(httpx, "AsyncClient", DummyClient)

    html = asyncio.run(
        mgr.handle_block(BlockResult.HTTP_403, session_id="s1", url="http://example.com")
    )

    assert html == "<html>ok</html>"
    ua.rotate.assert_called_once_with("s1")
    cookie.reset.assert_called_once_with("s1")
    cookie.update_from_response.assert_called_once()
    delay.prolong.assert_called_once_with()
