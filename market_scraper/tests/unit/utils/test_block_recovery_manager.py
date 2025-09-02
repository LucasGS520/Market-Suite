import asyncio
from unittest.mock import Mock

import pytest

from market_scraper.utils.block_recovery import BlockRecoveryManager
from shared.enums import BlockResult


def _setup_managers():
    ua = Mock()
    cookie = Mock()
    delay = Mock()
    mgr = BlockRecoveryManager(ua_manager=ua, cookie_manager=cookie, delay_manager=delay)
    return mgr, ua, cookie, delay

def test_handle_block_rotaciona_ua(monkeypatch):
    mgr, ua, cookie, delay = _setup_managers()
    monkeypatch.setattr("shared.utils.redis_client.suspend_scraping", lambda s: None)

    html = asyncio.run(mgr.handle_block(BlockResult.HTTP_403, session_id="s1", url="http://example.com"))

    assert html is None
    ua.rotate.assert_called_once_with("s1")
    cookie.reset.assert_called_once_with("s1")
    delay.prolong.assert_called_once_with()
