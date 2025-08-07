import importlib
import builtins

import pytest

from scraper_app.utils import audit_logger as audit_logger_mod

class DummyLogger:
    def __init__(self):
        self.called = False
        self.args = None
        self.kwargs = None

    def error(self, *a, **k):
        self.called = True
        self.args = a
        self.kwargs = k
        
def test_audit_logger_logs_error(monkeypatch, tmp_path):
    monkeypatch.setenv("AUDIT_LOG_DIR", str(tmp_path))
    audit_logger = importlib.reload(audit_logger_mod)

    dummy = DummyLogger()
    monkeypatch.setattr(audit_logger, "logger", dummy)

    def fake_open(*a, **k):
        raise IOError("disk full")

    monkeypatch.setattr(builtins, "open", fake_open)

    audit_logger.audit_scrape(stage="test", url="http://example.com", payload={}, html=None)

    assert dummy.called