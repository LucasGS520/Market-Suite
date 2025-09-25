import os
import asyncio
from unittest.mock import Mock

import pytest
import httpx

#Garantia necessária env vars para carregamento de configuração
os.environ.setdefault("DATABASE_URL", "sqlite:///test.db")
os.environ.setdefault("SECRET_KEY", "dummy")

from market_scraper.utils.block_recovery import BlockRecoveryManager
from shared.enums import BlockResult


@pytest.mark.parametrize(
    "block_type,expected",
    [
        (BlockResult.HTTP_429, 300),
        (BlockResult.HTTP_403, 900),
        (BlockResult.CAPTCHA, 1800)
    ]
)
def test_handle_block_invokes_managers(monkeypatch, block_type, expected):
    ua = Mock()
    ua.get_user_agent.return_value = "UA"
    cookie = Mock()
    cookie.get_cookies.return_value = {}
    delay = Mock()

    mgr = BlockRecoveryManager(ua_manager=ua, cookie_manager=cookie, delay_manager=delay)

    called = []
    monkeypatch.setattr("market_scraper.utils.block_recovery.suspend_scraping", lambda s: called.append(s))

    class DummyRobots:
        async def is_allowed(self, path, user_agent):
            return True
        
        async def get_crawl_delay(self, user_agent):
            return 0
        
    monkeypatch.setattr("market_scraper.utils.block_recovery.RobotsTxtManager", lambda base_url: DummyRobots())

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

                def raise_for_status(self):
                    return None

            return Resp()

    monkeypatch.setattr(httpx, "AsyncClient", DummyClient)

    html = asyncio.run(mgr.handle_block(block_type, session_id="sess", url="http://example.com"))

    ua.rotate.assert_called_once_with("sess")
    ua.get_user_agent.assert_called_once_with("sess")
    cookie.reset.assert_called_once_with("sess")
    cookie.get_cookies.assert_called_once_with("sess")
    cookie.update_from_response.assert_called_once()
    delay.prolong.assert_called_once_with()
    assert called == [expected]
    assert html == "<html>ok</html>"

def test_handle_block_uses_cache_when_request_fails(monkeypatch):
    identity = Mock()
    identity.get_user_agent.return_value = "UA"
    identity.get_cookies.return_value = {}
    delay = Mock()

    mgr = BlockRecoveryManager(identity_manager=identity, delay_manager=delay)

    monkeypatch.setattr("market_scraper.utils.block_recovery.suspend_scraping", lambda s: None)

    class DummyRobots:
        async def is_allowed(self, path, user_agent):
            return True
        
        async def get_crawl_delay(self, user_agent):
            return 0
        
    monkeypatch.setattr("market_scraper.utils.block_recovery.RobotsTxtManager", lambda base_url: DummyRobots())

    class FailClient:
        def __init__(self, *a, **k):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def get(self, url):
            raise httpx.HTTPError("falhou")

    monkeypatch.setattr(httpx, "AsyncClient", FailClient)

    class DummyCache:
        def get(self, *, marketplace, url):
            return {"html": "<cached></cached>"}

    monkeypatch.setattr("market_scraper.utils.block_recovery.IntelligentCacheManager", DummyCache)

    html = asyncio.run(mgr.handle_block(BlockResult.HTTP_429, session_id="sess", url="http://exemplo.com"))

    assert html == "<cached></cached>"
