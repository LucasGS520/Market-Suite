import json
from scraper_app.utils import audit_exporter
from scraper_app.utils import audit_logger


def test_metrics_counts(monkeypatch, tmp_path):
    day = tmp_path / "2024-01-01"
    day.mkdir(parents=True)
    with open(day / "ok.json", "w", encoding="utf-8") as f:
        json.dump({"stage": "ok"}, f)
    with open(day / "bad.json", "w", encoding="utf-8") as f:
        f.write("{invalid}")

    monkeypatch.setattr(audit_logger, "AUDIT_DIR", str(tmp_path))
    monkeypatch.setattr(audit_exporter, "AUDIT_DIR", str(tmp_path))

    resp = audit_exporter.metrics()
    body = resp.body.decode()
    assert 'audit_records_total{stage="ok"} 1.0' in body
    assert 'audit_errors_total{stage="unknown"} 1.0' in body
