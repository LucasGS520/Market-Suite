"""Testes unitários para ProductNormalizer.

Cobre normalize_name, normalize_source e normalize_url.
"""

from __future__ import annotations

import pytest

from market_scraper.post_processing.normalizers.product_normalizer import ProductNormalizer


@pytest.fixture
def normalizer() -> ProductNormalizer:
    return ProductNormalizer()


# ── normalize_name ─────────────────────────────────────────────────────────────

def test_normalize_name_strips_whitespace(normalizer):
    assert normalizer.normalize_name("  Notebook Gamer  ") == "Notebook Gamer"


def test_normalize_name_none_returns_none(normalizer):
    assert normalizer.normalize_name(None) is None


def test_normalize_name_empty_string_returns_none(normalizer):
    assert normalizer.normalize_name("") is None


def test_normalize_name_whitespace_only_returns_none(normalizer):
    assert normalizer.normalize_name("   ") is None


def test_normalize_name_accepts_numeric_coercion(normalizer):
    assert normalizer.normalize_name(12345) == "12345"


# ── normalize_source ───────────────────────────────────────────────────────────

def test_normalize_source_prefers_source_field(normalizer):
    payload = {"source": "mercadolivre.com.br", "marketplace": "other"}
    assert normalizer.normalize_source(payload) == "mercadolivre.com.br"


def test_normalize_source_falls_back_to_marketplace(normalizer):
    payload = {"marketplace": "amazon.com.br"}
    assert normalizer.normalize_source(payload) == "amazon.com.br"


def test_normalize_source_uses_fallback_arg(normalizer):
    assert normalizer.normalize_source({}, fallback="americanas.com.br") == "americanas.com.br"


def test_normalize_source_returns_empty_when_nothing(normalizer):
    assert normalizer.normalize_source({}) == ""


def test_normalize_source_ignores_none_source_field(normalizer):
    payload = {"source": None, "marketplace": "casasbahia.com.br"}
    assert normalizer.normalize_source(payload) == "casasbahia.com.br"


# ── normalize_url ──────────────────────────────────────────────────────────────

def test_normalize_url_strips_whitespace(normalizer):
    assert normalizer.normalize_url("  https://example.com/p  ") == "https://example.com/p"


def test_normalize_url_empty_string_returns_empty(normalizer):
    assert normalizer.normalize_url("") == ""


def test_normalize_url_valid_url_unchanged(normalizer):
    url = "https://www.mercadolivre.com.br/p/MLB-123"
    assert normalizer.normalize_url(url) == url
