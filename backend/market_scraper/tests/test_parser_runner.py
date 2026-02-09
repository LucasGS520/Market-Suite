""" Testes do executor de parsers com validação de dados """

from __future__ import annotations

from market_scraper.services.parser_runner import run_parser_with_validation
from market_scraper.services.synergic_pipeline import PipelineContext


def _parser_sucesso(html: str, url: str) -> dict[str, str]:
    """ Parser de exemplo que retorna um payload mínimo válido """
    return {
        "name": "Produto Teste",
        "current_price": "10.00",
        "url": url,
        "source": "exemplo.com",
    }


def _parser_vazio(html: str, url: str) -> None:
    """ Parser de exemplo que não encontra dados úteis """
    return None


def test_run_parser_with_validation_valido_atualiza_contexto() -> None:
    """ Valida que o runner atualiza o contexto quando o payload é válido """
    contexto = PipelineContext(
        url="https://exemplo.com/produto",
        source="exemplo.com",
        default_step_timeout=10.0,
    )
    contexto.set_html("<html></html>")

    sucesso, payload = run_parser_with_validation(
        parser=_parser_sucesso,
        context=contexto,
        step_name="parser_teste",
    )

    assert sucesso is True
    assert payload is not None
    assert contexto.data["name"] == "Produto Teste"
    assert contexto.data["current_price"] == "10.00"


def test_run_parser_with_validation_retorna_falso_quando_vazio() -> None:
    """ Garante que payload vazio não altera o contexto """
    contexto = PipelineContext(
        url="https://exemplo.com/produto",
        source="exemplo.com",
        default_step_timeout=10.0,
    )

    sucesso, payload = run_parser_with_validation(
        parser=_parser_vazio,
        context=contexto,
        step_name="parser_teste",
    )

    assert sucesso is False
    assert payload is None
    