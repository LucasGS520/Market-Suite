import uuid
from alert_app.models.models_scraping_errors import ScrapingError, ScrapingErrorType

class DummyLogger:
    def __init__(self):
        self.called = False

    def warning(self, *a, **k):
        self.called = True

def test_persistent_error_triggers_warning(monkeypatch):
    logger = DummyLogger()
    monkeypatch.setattr("structlog.get_logger", lambda name: logger)

    class DummyQuery:
        def __init__(self, db):
            self.db = db

        def filter(self, *a, **k):
            return self

        def count(self):
            return self.db.count

    class DummySession:
        def __init__(self):
            self.count = 5

        def add(self, obj):
            pass

        def commit(self):
            pass

        def refresh(self, obj):
            pass

        def query(self, cls):
            return DummyQuery(self)

    db = DummySession()
    ScrapingError.create(db, product_id=uuid.uuid4(), url="http://example.com", error_type=ScrapingErrorType.http_error)
    assert logger.called
