""" Testes unitários para utilitários de headers HTTP """

from __future__ import annotations

import pytest

from market_scraper.core.config_scraper import settings
from market_scraper.utils.headers import build_referer, REFERER_TEMPLATE_ERROR_EVENT


def test_build_referer_returns_none_when_template_missing(monkeypath: pytest.MonkeyPatch) -> None:
    """ Confirma que a função devolve ``None`` quando não há template configurado """
    monkeypath.setattr(settings, "SCRAPER_HEADERS_REFERER_TEMPLATE", "")
    assert build_referer("https://exemplo.com/item") is None

def test_build_referer_formats_domain_and_url(monkeypatch: pytest.MonkeyPatch) -> None:
    """ Garante interpolação correta do domínio e da URL informados """
    monkeypatch.setattr(settings, "SCRAPER_HEADERS_REFERER_TEMPLATE", "https://{domain}/origem?next={url}")
    referer = build_referer("https://loja.exemplo.com/produto")
    assert referer == "https://loja.exemplo.com/origem?next=https://loja.exemplo.com/produto"

def test_build_referer_logs_when_template_invalid(monkeypatch: pytest.MonkeyPatch) -> None:
    """ Assegura que erros de formatação sejam registrados para observabilidade """
    monkeypatch.setattr(settings, "SCRAPER_HEADERS_REFERER_TEMPLATE", "https://{dominio}/origem")
    captured: dict[str, object] = {}

    class DummyLogger:
        """ Logger simplificado que captura chamadas ao método warning """
        def warning(self, event: str, **kwargs: object) -> None:
            captured["event"] = event
            captured.update(kwargs)

    logger = DummyLogger()
    referer = build_referer(
        "https://loja.exemplo.com/produto",
        logger=logger,
        event_name=REFERER_TEMPLATE_ERROR_EVENT,
    )

    assert referer is None
    assert captured["event"] == REFERER_TEMPLATE_ERROR_EVENT
    assert "template" in captured
    assert "url" in captured
    