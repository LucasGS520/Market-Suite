"""Testes unitários para is_html_useful — validação de qualidade mínima de HTML.

Cobre todos os critérios canônicos:
    1. html=None → False
    2. status não-2xx → False
    3. tamanho < 1200 bytes → False
    4. marcador forte de anti-bot → False
    5. sinais de produto < 2 → False
    6. sinais de produto >= 2 → True
"""

from __future__ import annotations

import pytest

from backend.market_scraper.utils.html_quality import is_html_useful


# ── Fixtures de HTML ───────────────────────────────────────────────────────────

def _pad(content: str, target_bytes: int = 1500) -> str:
    """Garante que o HTML tem ao menos target_bytes bytes de conteúdo."""
    padding = "x" * max(0, target_bytes - len(content.encode("utf-8")))
    return content + padding


# HTML mínimo com 2 sinais: JSON-LD Product + preço
_HTML_PRODUCT_JSONLD = _pad(
    '<html><head>'
    '<script type="application/ld+json">{"@type":"Product","name":"TV","offers":{"@type":"Offer","price":"1999.90"}}</script>'
    '</head><body></body></html>'
)

# HTML com título og + sinal de preço (itemprop)
_HTML_PRODUCT_OG = _pad(
    '<html><head>'
    '<meta property="og:title" content="Produto X"/>'
    '<span itemprop="price">199,90</span>'
    '</head><body></body></html>'
)

# HTML com apenas 1 sinal: somente itemprop=price, sem JSON-LD nem título
_HTML_ONE_SIGNAL = _pad(
    '<html><head></head>'
    '<body><span itemprop="price">199,90</span></body></html>'
)

# HTML com marcador forte de Cloudflare
_HTML_CLOUDFLARE = _pad(
    '<html><body>var __cf_chl_opt = {"cType":"managed"};</body></html>'
)

# HTML com marcador de "verify you are human"
_HTML_VERIFY_HUMAN = _pad(
    '<html><body>Please verify you are human before continuing.</body></html>'
)


# ── None e status ────────────────────────────────────────────────────────────

def test_none_html_returns_false():
    assert is_html_useful(None, 200) is False


def test_status_404_returns_false():
    assert is_html_useful(_HTML_PRODUCT_JSONLD, 404) is False


def test_status_503_returns_false():
    assert is_html_useful(_HTML_PRODUCT_JSONLD, 503) is False


def test_status_200_passes():
    assert is_html_useful(_HTML_PRODUCT_JSONLD, 200) is True


def test_status_none_skips_check():
    """Quando http_status=None, critério de status é ignorado."""
    assert is_html_useful(_HTML_PRODUCT_JSONLD, None) is True


# ── Tamanho ────────────────────────────────────────────────────────────────────

def test_html_below_1200_bytes_returns_false():
    small = '<html><script type="application/ld+json">{"@type":"Product"}</script></html>'
    assert len(small.encode("utf-8")) < 1200
    assert is_html_useful(small, 200) is False


def test_html_exactly_at_limit_passes_if_signals_present():
    content = (
        '<html><head>'
        '<script type="application/ld+json">{"@type":"Product","name":"X","offers":{"@type":"Offer","price":"10"}}</script>'
        '</head><body>'
    )
    padded = content + ("x" * (1200 - len(content.encode("utf-8")))) + "</body></html>"
    assert len(padded.encode("utf-8")) >= 1200
    assert is_html_useful(padded, 200) is True


# ── Marcadores anti-bot fortes ────────────────────────────────────────────────

def test_cloudflare_chl_marker_returns_false():
    assert is_html_useful(_HTML_CLOUDFLARE, 200) is False


def test_verify_human_marker_returns_false():
    assert is_html_useful(_HTML_VERIFY_HUMAN, 200) is False


def test_captcha_class_marker_returns_false():
    html = _pad('<html><body><div class="captcha-container">solve this</div></body></html>')
    assert is_html_useful(html, 200) is False


# ── Sinais de produto ─────────────────────────────────────────────────────────

def test_two_signals_json_ld_and_offer():
    assert is_html_useful(_HTML_PRODUCT_JSONLD, 200) is True


def test_two_signals_og_title_and_price():
    assert is_html_useful(_HTML_PRODUCT_OG, 200) is True


def test_one_signal_returns_false():
    assert is_html_useful(_HTML_ONE_SIGNAL, 200) is False


def test_add_to_cart_counts_as_availability_signal():
    html = _pad(
        '<html><head><meta property="og:title" content="Produto"/></head>'
        '<body><button class="add-to-cart">Comprar</button></body></html>'
    )
    # og:title + comprar = 2 sinais
    assert is_html_useful(html, 200) is True


def test_no_signals_returns_false():
    html = _pad("<html><body>Página genérica sem produto</body></html>")
    assert is_html_useful(html, 200) is False


# ── Combinações ───────────────────────────────────────────────────────────────

@pytest.mark.parametrize("status", [301, 302, 400, 401, 403, 429, 500, 502, 503])
def test_non_2xx_always_false(status: int):
    assert is_html_useful(_HTML_PRODUCT_JSONLD, status) is False
