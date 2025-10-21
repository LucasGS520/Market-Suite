"""Testes para o script de diagnóstico de respostas ``no_result``."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

import pytest

from market_scraper.scripts.diagnose_no_result import (
    DiagnosticValidator,
    ParserReport,
    _format_excerpt,
    _load_urls,
    _prepare_output_dir,
    _run_parsers,
    _run_pipeline_with_html,
)


def _build_fake_parser(payload: dict[str, Any] | None) -> Callable[[str, str], dict[str, Any] | None]:
    """Gera parser fake que retorna payload fixo para validar o relatório."""

    def _parser(_: str, __: str) -> dict[str, Any] | None:
        return payload

    return _parser


def test_format_excerpt_removes_line_breaks() -> None:
    """Garante que o trecho de HTML retornado esteja linearizado."""

    html = "linha1\nlinha2\rlinha3"
    excerpt = _format_excerpt(html, length=10)
    assert "\n" not in excerpt
    assert "\r" not in excerpt
    assert excerpt == "linha1 lin"


def test_load_urls_combines_cli_and_file(tmp_path: Path) -> None:
    """Valida que URLs vindas por arquivo e CLI sejam deduplicadas preservando ordem."""

    file_path = tmp_path / "urls.txt"
    file_path.write_text("https://exemplo.com/1\nhttps://exemplo.com/2\n", encoding="utf-8")
    result = _load_urls([
        "https://exemplo.com/1",
        "https://exemplo.com/3",
    ], input_file=file_path)
    assert result == [
        "https://exemplo.com/1",
        "https://exemplo.com/3",
        "https://exemplo.com/2",
    ]


def test_run_parsers_reports_validation_issue() -> None:
    """Confere que a rejeição do validador seja exposta no relatório final."""

    validator = DiagnosticValidator()
    parsers = {
        "json_ld": _build_fake_parser({"name": "", "current_price": "10"}),
        "fallback": _build_fake_parser({"name": "Produto", "current_price": "invalid"}),
        "success": _build_fake_parser({"name": "Produto", "current_price": "12"}),
    }

    reports = _run_parsers("<html></html>", "https://exemplo.com", validator, parsers=parsers)

    assert reports["json_ld"]["status"] == "invalid"
    assert reports["json_ld"]["validation_issue"]["reason"] == "name_missing"
    assert reports["json_ld"]["validation_issue"]["reason_message"]
    assert reports["fallback"]["status"] == "invalid"
    assert reports["fallback"]["validation_issue"]["reason"] == "price_invalid"
    assert reports["fallback"]["validation_issue"]["reason_message"]
    assert reports["success"]["status"] == "valid"
    assert reports["success"]["validated_payload"]["name"] == "Produto"


def test_parser_report_to_dict_filters_none_values() -> None:
    """Assegura que campos nulos não sejam persistidos no dicionário final."""

    report = ParserReport(
        status="valid",
        raw_payload={"a": 1},
        validated_payload={"b": 2},
        validation_issue=None,
        error=None,
    )

    assert report.to_dict() == {
        "status": "valid",
        "raw_payload": {"a": 1},
        "validated_payload": {"b": 2},
    }

def test_prepare_output_dir_resets_existing_content(tmp_path: Path) -> None:
    """ Verifica que artefatos antigos sejam removidos antes de nova execução """
    output_dir = tmp_path / "diagnostics_output"
    nested_dir = output_dir / "old"
    nested_dir.mkdir(parents=True)
    (output_dir / "antigo.html").write_text("conteudo", encoding="utf-8")
    (nested_dir / "extra.txt").write_text("dados", encoding="utf-8")

    _prepare_output_dir(output_dir)

    assert list(output_dir.iterdir()) == []

@pytest.mark.asyncio()
async def test_run_pipeline_with_html_returns_strucutured_summary() -> None:
    """ Garante que o pipeline real seja executado e produza payload válido """
    html = """
    <html>
      <head>
        <meta property="og:title" content="Produto Teste" />
        <meta itemprop="price" content="1999.90" />
      </head>
      <body></body>
    </html>
    """
    url = "https://loja.exemplo/produto"

    result = await _run_pipeline_with_html(url, html)

    assert result["status"] == "success"
    assert result["payload"]["name"] == "Produto Teste"
    assert result["payload"]["current_price"] == "1999.90"
    step_names = [step["name"] for step in result["steps"]]
    assert step_names[0] == "fetch_html"
    assert "html_metadata_parser" in step_names
    assert result["context"]["url"] == url
