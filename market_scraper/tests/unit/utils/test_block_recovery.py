import os
import asyncio
from unittest.mock import Mock

import pytest

#Garantia necessária env vars para carregamento de configuração
os.environ.setdefault("DATABASE_URL", "sqlite:///test.db")
os.environ.setdefault("SECRET_KEY", "dummy")

from app.utils.block_recovery import BlockRecoveryManager


@pytest.mark.parametrize(
    "block_type,expected",
    [
        ("429", 300),
        ("403", 900),
        ("captcha", 1800)
    ]
)
def test_handle_block_invokes_managers(monkeypatch, block_type, expected):
    ua = Mock()
    cookie = Mock()
    delay = Mock()

    mgr = BlockRecoveryManager(ua_manager=ua, cookie_manager=cookie, delay_manager=delay)

    called = []
    monkeypatch.setattr("alert_app.utils.block_recovery.suspend_scraping", lambda s: called.append(s))

    asyncio.run(mgr.handle_block(block_type, session_id="sess"))

    ua.rotate.assert_called_once_with("sess")
    cookie.reset.assert_called_once_with("sess")
    delay.prolong.assert_called_once_with()
    assert called == [expected]
