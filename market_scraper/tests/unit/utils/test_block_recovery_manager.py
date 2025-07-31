import os
import asyncio
from unittest.mock import Mock

import pytest

#Garantia de variáveis de ambiente mínimas
os.environ.setdefault("DATABASE_URL", "sqlite:///test.db")
os.environ.setdefault("SECRET_KEY", "dummy")

from app.utils.block_recovery import BlockRecoveryManager
import app.metrics as metrics


class DummyCounter:
    def __init__(self):
        self.count = 0

    def inc(self):
        self.count += 1

def _setup_managers():
    ua = Mock()
    cookie = Mock()
    delay = Mock()
    mgr = BlockRecoveryManager(ua_manager=ua, cookie_manager=cookie, delay_manager=delay)
    return mgr, ua, cookie, delay

def test_recover_html_success(monkeypatch):
    mgr, ua, cookie, delay = _setup_managers()

    class DummyBrowser:
        async def fetch_html(self, url, session_id=None):
            return "<html></html>"

    class DummyCtx:
        async def __aenter__(self):
            return DummyBrowser()

        async def __aexit__(self, exc_type, exc, tb):
            pass

    monkeypatch.setattr("app.utils.block_recovery.get_playwright_client", lambda *a, **k: DummyCtx())
    monkeypatch.setattr("app.utils.block_recovery.suspend_scraping", lambda s: None)
    counter = DummyCounter()
    monkeypatch.setattr(metrics, "SCRAPER_BROWSER_RECOVERY_SUCCESS_TOTAL", counter)

    html = asyncio.run(mgr.handle_block("403", session_id="s1", url="http://example.com"))

    assert html == "<html></html>"
    assert counter.count == 1
    ua.rotate.assert_called_once_with("s1")
    cookie.reset.assert_called_once_with("s1")
    delay.prolong.assert_called_once_with()

def test_recover_html_failure(monkeypatch):
    mgr, ua, cookie, delay = _setup_managers()

    class DummyBrowser:
        async def fetch_html(self, url, session_id=None):
            raise RuntimeError("fail")

    class DummyCtx:
        async def __aenter__(self):
            return DummyBrowser()

        async def __aexit__(self, exc_type, exc, tb):
            pass

    monkeypatch.setattr("app.utils.block_recovery.get_playwright_client", lambda *a, **k: DummyCtx())
    monkeypatch.setattr("app.utils.block_recovery.suspend_scraping", lambda s: None)
    counter = DummyCounter()
    monkeypatch.setattr(metrics, "SCRAPER_BROWSER_RECOVERY_SUCCESS_TOTAL", counter)

    html = asyncio.run(mgr.handle_block("captcha", session_id="s2", url="http://example.com"))

    assert html is None
    assert counter.count == 0
    ua.rotate.assert_called_once_with("s2")
    cookie.reset.assert_called_once_with("s2")
    delay.prolong.assert_called_once_with()
