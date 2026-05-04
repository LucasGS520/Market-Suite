"""Testes unitários para availability_inference — heurísticas de disponibilidade.

Cobre:
  - infer_availability_from_http_status: mapeamento de status HTTP → InferenceResult
  - _detect_meli: paused vs unavailable sem sobreposição de strings
  - _detect_amazon, _detect_magalu, _detect_generic: detectores por domínio
  - detect_availability: prioridade status HTTP → metadados → domínio → genérico
"""

import pytest

from market_scraper.services.availability_inference import (
    InferenceResult,
    detect_availability,
    infer_availability_from_http_status,
)


# ── infer_availability_from_http_status ───────────────────────────────────────

@pytest.mark.parametrize("status,expected_status,confidence", [
    (404, "removed", "high"),
    (410, "removed", "high"),
    (451, "removed", "high"),
    (503, "temporarily_unavailable", "medium"),
    (401, "access_denied", "medium"),
    (403, "access_denied", "medium"),
])
def test_http_status_inference_known_codes(status, expected_status, confidence):
    result = infer_availability_from_http_status(status, "loja.com.br")
    assert result.availability is False
    assert result.last_status == expected_status
    assert result.confidence == confidence


@pytest.mark.parametrize("status", [200, 301, 302, 304, 400, 422, 429, 500, 502])
def test_http_status_inference_unknown_codes_return_none(status):
    result = infer_availability_from_http_status(status, "loja.com.br")
    assert result.availability is None
    assert result.confidence == "low"


# ── _detect_meli ──────────────────────────────────────────────────────────────

def test_meli_paused_detected():
    result, last_status = detect_availability(
        "anúncio pausado pelo vendedor", status_code=None, domain="mercadolivre.com.br"
    )
    assert result is False
    assert last_status == "paused"


def test_meli_unavailable_produto_nao_disponivel():
    result, last_status = detect_availability(
        "produto não disponível", status_code=None, domain="mercadolivre.com.br"
    )
    assert result is False
    assert last_status == "unavailable"


def test_meli_unavailable_indisponivel_no_momento():
    """'indisponível no momento' pertence ao branch unavailable, não paused."""
    result, last_status = detect_availability(
        "indisponível no momento", status_code=None, domain="mercadolivre.com.br"
    )
    assert result is False
    assert last_status == "unavailable"


def test_meli_no_false_positive_on_clean_page():
    result, last_status = detect_availability(
        "produto em estoque, compre agora", status_code=None, domain="mercadolivre.com.br"
    )
    assert result is None
    assert last_status is None


# ── _detect_amazon ────────────────────────────────────────────────────────────

@pytest.mark.parametrize("phrase", [
    "este item não está disponível",
    "item não disponível",
    "atualmente indisponível",
    "no momento este item está indisponível",
])
def test_amazon_unavailable_phrases(phrase):
    result, last_status = detect_availability(
        phrase, status_code=None, domain="amazon.com.br"
    )
    assert result is False
    assert last_status == "unavailable"


def test_amazon_no_false_positive():
    result, _ = detect_availability(
        "adicionar ao carrinho", status_code=None, domain="amazon.com.br"
    )
    assert result is None


# ── _detect_magalu ────────────────────────────────────────────────────────────

@pytest.mark.parametrize("phrase", [
    "produto indisponível",
    "avise-me quando chegar",
    "esgotado",
])
def test_magalu_unavailable_phrases(phrase):
    result, _ = detect_availability(phrase, status_code=None, domain="magazineluiza.com.br")
    assert result is False


# ── detect_availability: prioridade e fallback ────────────────────────────────

def test_http_status_takes_priority_over_html():
    """Status 404 deve retornar removed mesmo com HTML de produto disponível."""
    result, last_status = detect_availability(
        "produto em estoque", status_code=404, domain="loja.com.br"
    )
    assert result is False
    assert last_status == "removed"


def test_no_html_no_relevant_status_returns_none():
    result, last_status = detect_availability(None, status_code=200, domain="loja.com.br")
    assert result is None
    assert last_status is None


def test_metadata_schema_out_of_stock_detected():
    html = 'availability": "OutOfStock"'
    result, last_status = detect_availability(html, status_code=None, domain="loja.com.br")
    assert result is False
    assert last_status == "unavailable"


def test_generic_detector_runs_when_no_domain_match():
    result, last_status = detect_availability(
        "produto esgotado", status_code=None, domain="outra-loja.com.br"
    )
    assert result is False
    assert last_status == "unavailable"


def test_generic_detector_sold_out():
    result, _ = detect_availability(
        "sold out", status_code=None, domain="loja.com.br"
    )
    assert result is False


def test_unknown_domain_and_available_html_returns_none():
    result, last_status = detect_availability(
        "adicionar ao carrinho", status_code=200, domain="loja-desconhecida.com.br"
    )
    assert result is None
    assert last_status is None
