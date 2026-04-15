"""Testes unitários para ResponseClassifier e detect_anti_bot_pattern.

Cada teste corresponde a uma linha da tabela de decisão documentada em
``services/response_classifier.py``. Todos são síncronos — o classificador
não realiza I/O.
"""

from __future__ import annotations

import httpx
import pytest

from market_scraper.services.response_classifier import (
    ClassificationAction,
    ClassificationResult,
    ResponseClassifier,
    detect_anti_bot_pattern,
)


# ─────────────────────────────────────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────────────────────────────────────

_NORMAL_HTML = "<html><body>" + "x" * 2048 + "</body></html>"  # ~2 KB
_SMALL_HTML  = "<html><body>ok</body></html>"                  # << 1 KB
_EMPTY_HTML  = ""


@pytest.fixture
def classifier() -> ResponseClassifier:
    return ResponseClassifier()


# ─────────────────────────────────────────────────────────────────────────────
# Tabela de decisão — respostas 2xx
# ─────────────────────────────────────────────────────────────────────────────

def test_classify_success_normal_html(classifier):
    """200 + HTML normal (≥1KB) → SUCCESS."""
    result = classifier.classify(http_status=200, html=_NORMAL_HTML, error=None)

    assert result.action == ClassificationAction.SUCCESS
    assert result.next_layer is None
    assert result.reason == "html_valid"


def test_classify_scale_to_layer3_when_html_empty(classifier):
    """200 + HTML vazio → SCALE para Camada 3."""
    result = classifier.classify(http_status=200, html=_EMPTY_HTML, error=None)

    assert result.action == ClassificationAction.SCALE
    assert result.next_layer == 3
    assert result.reason == "html_empty"


def test_classify_scale_to_layer3_when_html_too_small(classifier):
    """200 + HTML abaixo de 1KB → SCALE para Camada 3."""
    result = classifier.classify(http_status=200, html=_SMALL_HTML, error=None)

    assert result.action == ClassificationAction.SCALE
    assert result.next_layer == 3
    assert result.reason == "html_empty"


def test_classify_scale_to_layer3_when_html_is_none(classifier):
    """200 + html=None → SCALE para Camada 3."""
    result = classifier.classify(http_status=200, html=None, error=None)

    assert result.action == ClassificationAction.SCALE
    assert result.next_layer == 3
    assert result.reason == "html_empty"


# ─────────────────────────────────────────────────────────────────────────────
# Tabela de decisão — anti-bot
# ─────────────────────────────────────────────────────────────────────────────

def test_classify_scale_when_cloudflare_challenge_detected(classifier):
    """200 + HTML com challenges.cloudflare.com → SCALE para Camada 3."""
    html = _NORMAL_HTML + '<script src="https://challenges.cloudflare.com/turnstile/v0/api.js"></script>'
    result = classifier.classify(http_status=200, html=html, error=None)

    assert result.action == ClassificationAction.SCALE
    assert result.next_layer == 3
    assert result.reason == "anti_bot_page"
    assert result.telemetry.get("anti_bot_pattern") == "cloudflare_challenge"


def test_classify_scale_when_cf_bm_cookie_detected(classifier):
    """200 + HTML com __cf_bm → SCALE (fingerprint Cloudflare)."""
    html = _NORMAL_HTML + '<input name="__cf_bm" type="hidden" value="abc" />'
    result = classifier.classify(http_status=200, html=html, error=None)

    assert result.action == ClassificationAction.SCALE
    assert result.next_layer == 3
    assert result.reason == "anti_bot_page"


def test_classify_scale_when_recaptcha_detected(classifier):
    """200 + HTML com recaptcha/api.js → SCALE para Camada 3."""
    html = _NORMAL_HTML + '<script src="https://www.google.com/recaptcha/api.js"></script>'
    result = classifier.classify(http_status=200, html=html, error=None)

    assert result.action == ClassificationAction.SCALE
    assert result.next_layer == 3
    assert result.reason == "anti_bot_page"
    assert result.telemetry.get("anti_bot_pattern") == "captcha_challenge"


def test_classify_scale_when_mercadolivre_challenge_detected(classifier):
    """200 + suspicious-traffic-frontend (Mercado Livre) → SCALE."""
    html = _NORMAL_HTML + '<div id="suspicious-traffic-frontend"></div>'
    result = classifier.classify(http_status=200, html=html, error=None)

    assert result.action == ClassificationAction.SCALE
    assert result.next_layer == 3
    assert result.telemetry.get("anti_bot_pattern") == "mercadolivre_challenge"


def test_classify_scale_when_perimeterx_detected(classifier):
    """200 + _pxcaptcha (PerimeterX) → SCALE."""
    html = _NORMAL_HTML + '<div id="_pxcaptcha"></div>'
    result = classifier.classify(http_status=200, html=html, error=None)

    assert result.action == ClassificationAction.SCALE
    assert result.next_layer == 3
    assert result.telemetry.get("anti_bot_pattern") == "perimeterx_challenge"


# ─────────────────────────────────────────────────────────────────────────────
# Tabela de decisão — erros de status HTTP
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("status", [404, 410])
def test_classify_reject_on_not_found(classifier, status):
    """404/410 → REJECT definitivo (sem escalonamento)."""
    result = classifier.classify(http_status=status, html=None, error=None)

    assert result.action == ClassificationAction.REJECT
    assert result.next_layer is None
    assert result.reason == "not_found"


def test_classify_scale_to_layer2_on_429(classifier):
    """429 → SCALE (Camada 2 no futuro; por ora escala para 3 no MVP)."""
    result = classifier.classify(http_status=429, html=None, error=None)

    assert result.action == ClassificationAction.SCALE
    # MVP: Camada 2 não implementada, redireciona para 3
    assert result.next_layer == 3
    assert result.reason == "rate_limited"
    assert result.telemetry.get("layer2_deferred") is True


@pytest.mark.parametrize("status", [403, 405, 406])
def test_classify_scale_to_layer3_on_access_denied(classifier, status):
    """403/405/406 → SCALE para Camada 3."""
    result = classifier.classify(http_status=status, html=None, error=None)

    assert result.action == ClassificationAction.SCALE
    assert result.next_layer == 3
    assert result.reason == "access_denied"


@pytest.mark.parametrize("status", [500, 502, 503, 504])
def test_classify_scale_to_layer3_on_server_error(classifier, status):
    """5xx → SCALE para Camada 3."""
    result = classifier.classify(http_status=status, html=None, error=None)

    assert result.action == ClassificationAction.SCALE
    assert result.next_layer == 3
    assert result.reason == "server_error"


def test_classify_reject_other_4xx(classifier):
    """4xx não mapeado (ex: 422) → REJECT defensivo."""
    result = classifier.classify(http_status=422, html=None, error=None)

    assert result.action == ClassificationAction.REJECT
    assert result.reason == "client_error"


# ─────────────────────────────────────────────────────────────────────────────
# Tabela de decisão — erros de transporte (sem status HTTP)
# ─────────────────────────────────────────────────────────────────────────────

def test_classify_timeout_escalates(classifier):
    """Timeout → SCALE para Camada 3."""
    req = httpx.Request("GET", "https://example.com")
    error = httpx.ReadTimeout("timed out", request=req)

    result = classifier.classify(http_status=None, html=None, error=error)

    assert result.action == ClassificationAction.SCALE
    assert result.next_layer == 3
    assert result.reason == "timeout"


def test_classify_connect_error_escalates(classifier):
    """ConnectError → SCALE para Camada 3."""
    req = httpx.Request("GET", "https://example.com")
    error = httpx.ConnectError("connection refused", request=req)

    result = classifier.classify(http_status=None, html=None, error=error)

    assert result.action == ClassificationAction.SCALE
    assert result.next_layer == 3
    assert result.reason == "connection_error"


def test_classify_connect_timeout_escalates(classifier):
    """ConnectTimeout → SCALE para Camada 3 (timeout de handshake)."""
    req = httpx.Request("GET", "https://example.com")
    error = httpx.ConnectTimeout("connect timed out", request=req)

    result = classifier.classify(http_status=None, html=None, error=error)

    assert result.action == ClassificationAction.SCALE
    assert result.next_layer == 3
    assert result.reason == "timeout"


def test_classify_unknown_network_error_escalates(classifier):
    """Erro de rede genérico → SCALE defensivo para Camada 3."""
    req = httpx.Request("GET", "https://example.com")
    error = httpx.RemoteProtocolError("unexpected disconnect", request=req)

    result = classifier.classify(http_status=None, html=None, error=error)

    assert result.action == ClassificationAction.SCALE
    assert result.next_layer == 3


# ─────────────────────────────────────────────────────────────────────────────
# Testes de detect_anti_bot_pattern isolado
# ─────────────────────────────────────────────────────────────────────────────

def test_detect_anti_bot_pattern_returns_none_for_clean_html():
    """HTML limpo → None (sem padrão detectado)."""
    assert detect_anti_bot_pattern(_NORMAL_HTML) is None


def test_detect_anti_bot_pattern_detects_cloudflare():
    """challenges.cloudflare.com → cloudflare_challenge."""
    html = '<script src="https://challenges.cloudflare.com/api.js"></script>'
    assert detect_anti_bot_pattern(html) == "cloudflare_challenge"


def test_detect_anti_bot_pattern_detects_recaptcha():
    """recaptcha/api.js → captcha_challenge."""
    html = '<script src="https://www.google.com/recaptcha/api.js"></script>'
    assert detect_anti_bot_pattern(html) == "captcha_challenge"


def test_detect_anti_bot_pattern_is_case_insensitive():
    """A detecção ignora maiúsculas/minúsculas."""
    html = _NORMAL_HTML + "<DIV ID='SUSPICIOUS-TRAFFIC-FRONTEND'></DIV>"
    assert detect_anti_bot_pattern(html) == "mercadolivre_challenge"


# ─────────────────────────────────────────────────────────────────────────────
# Testes da estrutura ClassificationResult
# ─────────────────────────────────────────────────────────────────────────────

def test_classification_result_is_immutable(classifier):
    """ClassificationResult é frozen — não permite mutação acidental."""
    result = classifier.classify(http_status=200, html=_NORMAL_HTML, error=None)

    with pytest.raises((AttributeError, TypeError)):
        result.action = ClassificationAction.REJECT  # type: ignore[misc]


def test_telemetry_html_size_populated_on_success(classifier):
    """Telemetria de sucesso inclui html_size_bytes."""
    result = classifier.classify(http_status=200, html=_NORMAL_HTML, error=None)

    assert "html_size_bytes" in result.telemetry
    assert result.telemetry["html_size_bytes"] > 0


def test_telemetry_http_status_populated_on_error(classifier):
    """Telemetria de erro inclui http_status."""
    result = classifier.classify(http_status=404, html=None, error=None)

    assert result.telemetry.get("http_status") == 404
