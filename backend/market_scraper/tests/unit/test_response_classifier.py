"""Testes unitários para ResponseClassifier e detect_anti_bot_pattern.

Cada teste corresponde a uma linha da tabela de decisão documentada em
``services/response_classifier.py``. Todos são síncronos — o classificador
não realiza I/O.
"""

from __future__ import annotations

import httpx
import pytest
from pathlib import Path

from market_scraper.services.response_classifier import (
    ClassificationAction,
    ClassificationResult,
    ResponseClassifier,
    detect_anti_bot_pattern,
    has_product_signals,
)


# ─────────────────────────────────────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────────────────────────────────────

_NORMAL_HTML = "<html><body>" + "x" * 2048 + "</body></html>"  # ~2 KB sem sinais de produto
_PRODUCT_HTML = (
    "<html><head>"
    '<script type="application/ld+json">{"@type":"Product","name":"Produto","offers":{"price":"999"}}</script>'
    "</head><body>" + "x" * 2048 + "</body></html>"
)  # ~2 KB com JSON-LD de produto
_SMALL_HTML  = "<html><body>ok</body></html>"                  # << 1 KB
_EMPTY_HTML  = ""

# Anti-bot com sinais de produto (JSON-LD presente) → sucesso degradado esperado
_CHALLENGE_WITH_PRODUCT_HTML = (
    "<html><head>"
    '<script type="application/ld+json">{"@type":"Product","name":"Notebook","offers":{"price":"999"}}</script>'
    '<script src="https://challenges.cloudflare.com/turnstile/v0/api.js"></script>'
    "</head><body>"
    + "x" * 2048
    + "</body></html>"
)
# Anti-bot sem sinais de produto → SCALE esperado
_CHALLENGE_NO_PRODUCT_HTML = _NORMAL_HTML + '<script src="https://challenges.cloudflare.com/turnstile/v0/api.js"></script>'


@pytest.fixture
def classifier() -> ResponseClassifier:
    return ResponseClassifier()


# ─────────────────────────────────────────────────────────────────────────────
# Tabela de decisão — respostas 2xx
# ─────────────────────────────────────────────────────────────────────────────

def test_classify_success_normal_html(classifier):
    """200 + HTML com sinais de produto (≥1KB) → SUCCESS."""
    result = classifier.classify(http_status=200, html=_PRODUCT_HTML, error=None)

    assert result.action == ClassificationAction.SUCCESS
    assert result.next_layer is None
    assert result.reason == "html_valid"


def test_classify_scale_when_html_valid_but_no_product_signals(classifier):
    """200 + HTML grande sem sinais de produto → SCALE (provavelmente shell JS)."""
    result = classifier.classify(http_status=200, html=_NORMAL_HTML, error=None)

    assert result.action == ClassificationAction.SCALE
    assert result.next_layer == 3
    assert result.reason == "html_without_product_signals"


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


def test_classify_reject_when_mercadolivre_terminal_challenge_detected(classifier):
    """200 + suspicious-traffic-frontend (Mercado Livre, padrão terminal) → REJECT imediato.

    Padrão terminal não admite recuperação via browser com a mesma identidade.
    Fail-fast preserva o budget de browser para URLs recuperáveis.
    """
    html = _NORMAL_HTML + '<div id="suspicious-traffic-frontend"></div>'
    result = classifier.classify(http_status=200, html=html, error=None)

    assert result.action == ClassificationAction.REJECT
    assert result.next_layer is None
    assert result.reason == "anti_bot_blocked"
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


def test_classify_remote_protocol_error_escalates(classifier):
    """RemoteProtocolError → connection_error → SCALE para browser.

    Servidor fechou a conexão inesperadamente — pode ser TLS fingerprinting.
    Browser com fingerprint diferente pode contornar; escalamento é defensivo.
    """
    req = httpx.Request("GET", "https://example.com")
    error = httpx.RemoteProtocolError("unexpected disconnect", request=req)

    result = classifier.classify(http_status=None, html=None, error=error)

    assert result.action == ClassificationAction.SCALE
    assert result.next_layer == 3
    assert result.reason == "connection_error"


def test_classify_unknown_network_error_rejects(classifier):
    """Erro de transporte desconhecido (catch-all) → REJECT definitivo.

    Exceções não identificadas como timeout nem connection_error usam a mesma
    rede e DNS que o browser — escalar não recupera. Falha rápida.
    """
    error = OSError("network failure")  # não é httpx — cai no catch-all

    result = classifier.classify(http_status=None, html=None, error=error)

    assert result.action == ClassificationAction.REJECT
    assert result.next_layer is None
    assert result.reason == "network_error"


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
    result = classifier.classify(http_status=200, html=_PRODUCT_HTML, error=None)

    with pytest.raises((AttributeError, TypeError)):
        result.action = ClassificationAction.REJECT  # type: ignore[misc]


def test_telemetry_html_size_populated_on_success(classifier):
    """Telemetria de sucesso inclui html_size_bytes."""
    result = classifier.classify(http_status=200, html=_PRODUCT_HTML, error=None)

    assert "html_size_bytes" in result.telemetry
    assert result.telemetry["html_size_bytes"] > 0


def test_telemetry_http_status_populated_on_error(classifier):
    """Telemetria de erro inclui http_status."""
    result = classifier.classify(http_status=404, html=None, error=None)

    assert result.telemetry.get("http_status") == 404


# ─────────────────────────────────────────────────────────────────────────────
# Fase 5 — anti_bot_degraded: anti-bot + sinais de produto → SUCCESS degradado
# ─────────────────────────────────────────────────────────────────────────────

def test_classify_degraded_success_when_antibot_with_product_signals(classifier):
    """Anti-bot + JSON-LD de produto → SUCCESS com reason='anti_bot_degraded'.

    Página tem overlay de challenge mas expõe JSON-LD: parsers têm chance real de
    extrair dados. Playwright não deve ser acionado.
    """
    result = classifier.classify(http_status=200, html=_CHALLENGE_WITH_PRODUCT_HTML, error=None)

    assert result.action == ClassificationAction.SUCCESS
    assert result.next_layer is None
    assert result.reason == "anti_bot_degraded"
    assert result.telemetry.get("anti_bot_pattern") == "cloudflare_challenge"


def test_classify_scale_when_antibot_without_product_signals(classifier):
    """Anti-bot sem sinais de produto → SCALE para Playwright (comportamento original)."""
    result = classifier.classify(http_status=200, html=_CHALLENGE_NO_PRODUCT_HTML, error=None)

    assert result.action == ClassificationAction.SCALE
    assert result.next_layer == 3
    assert result.reason == "anti_bot_page"


# ─────────────────────────────────────────────────────────────────────────────
# Testes de has_product_signals isolado
# ─────────────────────────────────────────────────────────────────────────────

def test_has_product_signals_detects_ld_json():
    """HTML com application/ld+json → True."""
    html = '<script type="application/ld+json">{"@type":"Product"}</script>'
    assert has_product_signals(html) is True


def test_has_product_signals_detects_itemprop_price():
    """HTML com itemprop="price" → True."""
    html = '<span itemprop="price">R$ 99,90</span>'
    assert has_product_signals(html) is True


def test_has_product_signals_ignores_offers_key():
    """'"offers"' sozinho é genérico demais (analytics/config) → False.

    Padrão removido para evitar falso-positivo em challenge pages que incluem
    JSON de configuração com chave "offers". Usar 'application/ld+json' + @type.
    """
    html = '{"offers": {"price": "100", "priceCurrency": "BRL"}}'
    assert has_product_signals(html) is False


def test_has_product_signals_false_for_plain_html():
    """HTML sem nenhum sinal de produto → False."""
    assert has_product_signals(_NORMAL_HTML) is False


def test_has_product_signals_false_for_empty_html():
    """HTML vazio → False."""
    assert has_product_signals("") is False


# ─────────────────────────────────────────────────────────────────────────────
# Novos sinais de produto (Fase 2 — expansão de _PRODUCT_SIGNAL_PATTERNS)
# ─────────────────────────────────────────────────────────────────────────────

def test_has_product_signals_detects_ui_pdp_title():
    """Classe ui-pdp-title (título de produto do Mercado Livre) → True."""
    html = '<h1 class="ui-pdp-title">Notebook Lenovo</h1>'
    assert has_product_signals(html) is True


def test_has_product_signals_detects_andes_money_amount():
    """Componente andes-money-amount (preço do Mercado Livre) → True."""
    html = '<span class="andes-money-amount__fraction">3.499</span>'
    assert has_product_signals(html) is True


def test_has_product_signals_detects_og_price_amount():
    """Meta og:price:amount (Open Graph genérico) → True."""
    html = '<meta property="og:price:amount" content="199.90" />'
    assert has_product_signals(html) is True


def test_has_product_signals_ignores_json_price_key():
    """'"price":' genérico não é sinal suficiente → False.

    Chave "price" aparece em scripts de analytics, configuração e challenge pages.
    Falso-positivo confirmado em staging (Mercado Livre challenge).
    """
    html = '<script>window.__STATE__ = {"price": 999, "name": "Produto"}</script>'
    assert has_product_signals(html) is False


def test_has_product_signals_ignores_productpage_schema():
    """'productpage' sozinho é genérico demais → False.

    Padrão removido: aparece em títulos, textos de página e SEO sem relação
    com dados estruturados de produto extraíveis pelos parsers.
    """
    html = '<body itemtype="https://schema.org/ProductPage">'
    assert has_product_signals(html) is False


def test_has_product_signals_ignores_price_tag():
    """'price-tag' é classe CSS genérica, não sinal de produto confiável → False.

    Classe presente em temas/templates de e-commerce sem vínculo direto
    com dados estruturados; removida para reduzir falso-positivos.
    """
    html = '<span class="price-tag-fraction">3499</span>'
    assert has_product_signals(html) is False


# ─────────────────────────────────────────────────────────────────────────────
# Classificação degradada com sinal ML específico
# ─────────────────────────────────────────────────────────────────────────────

def test_classify_mercadolivre_challenge_with_product_class_returns_degraded(classifier):
    """ML challenge (suspicious-traffic-frontend) + ui-pdp-title → SUCCESS degradado.

    Regressão: o classificador NÃO deve escalar para Playwright quando o HTML
    já tem sinais de produto, mesmo que tenha o padrão anti-bot do ML.
    """
    html = (
        '<div id="suspicious-traffic-frontend"></div>'
        '<h1 class="ui-pdp-title">Console PlayStation 5</h1>'
        '<span class="andes-money-amount__fraction">4.499</span>'
        + "x" * 2048
    )
    result = classifier.classify(http_status=200, html=html, error=None)

    assert result.action == ClassificationAction.SUCCESS
    assert result.reason == "anti_bot_degraded"
    assert result.telemetry.get("anti_bot_pattern") == "mercadolivre_challenge"


# ─────────────────────────────────────────────────────────────────────────────
# Regressão — fixtures HTML reais (Fase 3)
# ─────────────────────────────────────────────────────────────────────────────

_FIXTURES_DIR = Path(__file__).resolve().parent.parent / "fixtures"


def _load_fixture(name: str) -> str:
    return (_FIXTURES_DIR / name).read_text(encoding="utf-8")


def test_fixture_js_challenge_detected_as_anti_bot():
    """response_js_challenge.html → detect_anti_bot_pattern retorna padrão cloudflare.

    Regressão: garante que a fixture de challenge é sempre detectada como anti-bot
    e não escapa como HTML válido de produto.
    """
    html = _load_fixture("response_js_challenge.html")
    pattern = detect_anti_bot_pattern(html)
    assert pattern is not None
    assert "cloudflare" in pattern


def test_fixture_js_challenge_has_no_product_signals():
    """response_js_challenge.html NÃO contém sinais de produto de alta confiança.

    Regressão: padrões genéricos removidos em Fase 2 não devem causar falso-positivo
    neste HTML de challenge (que pode ter scripts com chaves JSON genéricas).
    """
    html = _load_fixture("response_js_challenge.html")
    assert has_product_signals(html) is False


def test_fixture_product_success_has_product_signals():
    """product_success.html contém itemprop="price" → has_product_signals retorna True.

    Regressão: HTML de produto real deve sempre ativar early-exit pelo sinal itemprop.
    """
    html = _load_fixture("product_success.html")
    assert has_product_signals(html) is True
