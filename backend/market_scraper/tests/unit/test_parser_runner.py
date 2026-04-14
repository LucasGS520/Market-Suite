from __future__ import annotations

from market_scraper.services import parser_runner as parser_runner_module
from market_scraper.services.synergic_pipeline import PipelineContext
from market_scraper.utils.validator import ValidationResult


class _LoggerSpy:
    def __init__(self) -> None:
        self.warning_calls: list[tuple[str, dict[str, object]]] = []
        self.info_calls: list[tuple[str, dict[str, object]]] = []

    def warning(self, event: str, **kwargs) -> None:
        self.warning_calls.append((event, kwargs))

    def info(self, event: str, **kwargs) -> None:
        self.info_calls.append((event, kwargs))


def test_run_parser_with_validation_updates_context_with_validated_payload(monkeypatch):
    context = PipelineContext(
        url="https://example.com/product",
        source="example.com",
        default_step_timeout=1.0,
        html="<html>produto indisponivel</html>",
    )
    context.data["http_status"] = 404
    context.data["dump_path"] = "/tmp/dump.html"
    logger_spy = _LoggerSpy()
    validation_call: dict[str, object] = {}

    def fake_parser(html: str, url: str):
        return {"name": "Produto validado"}

    def fake_detect_availability(html: str, *, status_code: int | None, domain: str | None):
        assert status_code == 404
        assert domain == "example.com"
        return False, "removed"

    def fake_validate(**kwargs):
        validation_call.update(kwargs)
        return ValidationResult(
            payload={
                "name": "Produto validado",
                "current_price": None,
                "currency": "BRL",
                "availability": False,
                "last_status": "removed",
                "url": "https://example.com/product",
                "source": "example.com",
            }
        )

    monkeypatch.setattr(parser_runner_module, "detect_availability", fake_detect_availability)
    monkeypatch.setattr(parser_runner_module, "logger", logger_spy)
    monkeypatch.setattr(parser_runner_module._validator, "validate", fake_validate)

    ok, payload = parser_runner_module.run_parser_with_validation(
        parser=fake_parser,
        context=context,
        step_name="generic_fallback_parser",
    )

    assert ok is True
    assert payload is not None
    assert payload["last_status"] == "removed"
    assert validation_call["dump_path"] == "/tmp/dump.html"
    assert validation_call["inferred_availability"] is False
    assert validation_call["inferred_last_status"] == "removed"
    assert context.data["name"] == "Produto validado"
    assert context.data["current_price"] is None
    assert context.data["currency"] == "BRL"
    assert context.data["availability"] is False
    assert context.data["last_status"] == "removed"
    assert context.data["payload"]["source"] == "example.com"
    assert context.data["availability_inferred"] is False
    assert context.data["last_status_inferred"] == "removed"
    assert logger_spy.info_calls
    assert logger_spy.info_calls[0][0] == "availability_inferred_before_validation"


def test_run_parser_with_validation_records_validation_failure_metadata(monkeypatch):
    context = PipelineContext(
        url="https://example.com/product",
        source="example.com",
        default_step_timeout=1.0,
        html="<html>sem dados</html>",
    )
    context.data["dump_path"] = "/tmp/invalid.html"

    def fake_parser(html: str, url: str):
        return {"name": ""}

    monkeypatch.setattr(
        parser_runner_module,
        "detect_availability",
        lambda html, *, status_code, domain: (None, None),
    )
    monkeypatch.setattr(
        parser_runner_module._validator,
        "validate",
        lambda **kwargs: ValidationResult(
            payload=None,
            reason_code="name_missing",
            reason_message="Campo name ausente ou vazio",
        ),
    )

    ok, payload = parser_runner_module.run_parser_with_validation(
        parser=fake_parser,
        context=context,
        step_name="json_ld_parser",
    )

    assert ok is False
    assert payload is None
    assert context.data["validation_failures"] == [
        {
            "step": "json_ld_parser",
            "reason_code": "name_missing",
            "reason_message": "Campo name ausente ou vazio",
            "parser_name": "fake_parser",
            "dump_path": "/tmp/invalid.html",
        }
    ]


def test_run_parser_with_validation_returns_false_when_parser_raises(monkeypatch):
    context = PipelineContext(
        url="https://example.com/product",
        source="example.com",
        default_step_timeout=1.0,
        html="<html>boom</html>",
    )
    logger_spy = _LoggerSpy()

    def fake_parser(html: str, url: str):
        raise RuntimeError("parser exploded")

    monkeypatch.setattr(parser_runner_module, "logger", logger_spy)

    ok, payload = parser_runner_module.run_parser_with_validation(
        parser=fake_parser,
        context=context,
        step_name="html_metadata_parser",
    )

    assert ok is False
    assert payload is None
    assert logger_spy.warning_calls
    event, fields = logger_spy.warning_calls[0]
    assert event == "parser_execution_error"
    assert fields["step"] == "html_metadata_parser"
    assert fields["result"] == "error"
    assert fields["domain"] == "example.com"
    assert fields["error"] == "parser exploded"
