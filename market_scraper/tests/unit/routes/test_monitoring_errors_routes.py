import types
from uuid import UUID

from alert_app.routes import routes_monitoring_errors as r


def _request():
    return types.SimpleNamespace(url=types.SimpleNamespace(path="/monitoring_errors/errors"), method="GET")

def test_list_errors_scraping_for_product(monkeypatch):
    captured = {}

    def fake_get(db, pid, limit):
        captured["args"] = (pid, limit)
        return ["e"]

    monkeypatch.setattr(r, "get_scraping_errors_for_product", fake_get)
    monkeypatch.setattr(r, "get_recent_scraping_errors", lambda db, limit: [])

    res = r.list_errors_scraping(_request(), db=None, limit=10, product_id=UUID("123e4567-e89b-12d3-a456-426655440000"), user=types.SimpleNamespace(id="u"))

    assert res == ["e"]
    assert captured["args"] == (UUID("123e4567-e89b-12d3-a456-426655440000"), 10)
