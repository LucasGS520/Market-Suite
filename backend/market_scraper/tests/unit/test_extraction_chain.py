from __future__ import annotations

from market_scraper.domain.dtos import ParseResult
from market_scraper.extraction.extraction_chain import ExtractionChain


def test_extraction_chain_uses_strict_final_order(monkeypatch):
    calls: list[str] = []

    def fake_extruct(html: str, url: str):
        calls.append("extruct")
        return None

    def fake_parsel(html: str, url: str):
        calls.append("parsel")
        return None

    def fake_beautifulsoup(html: str, url: str):
        calls.append("beautifulsoup")
        return {"name": "Notebook Gamer", "current_price": "4999.90", "url": url}

    monkeypatch.setattr("market_scraper.extraction.extraction_chain.parse_with_extruct", fake_extruct)
    monkeypatch.setattr("market_scraper.extraction.extraction_chain.parse_with_parsel", fake_parsel)
    monkeypatch.setattr(
        "market_scraper.extraction.extraction_chain.parse_with_beautifulsoup",
        fake_beautifulsoup,
    )

    result = ExtractionChain().run(
        "<html><body>produto</body></html>",
        "https://produto.mercadolivre.com.br/MLB-1",
        "mercadolivre.com.br",
        http_status=200,
    )

    assert result.succeeded is True
    assert result.parser_used == "beautifulsoup"
    assert [attempt.parser_name for attempt in result.attempts] == ["extruct", "parsel", "beautifulsoup"]
    assert calls == ["extruct", "parsel", "beautifulsoup"]
    assert result.payload is not None
    assert result.payload["name"] == "Notebook Gamer"
    assert result.payload["current_price"] == "4999.90"


def test_extraction_chain_stops_on_parsel_success(monkeypatch):
    monkeypatch.setattr(
        "market_scraper.extraction.extraction_chain.parse_with_extruct",
        lambda html, url: None,
    )
    monkeypatch.setattr(
        "market_scraper.extraction.extraction_chain.parse_with_parsel",
        lambda html, url: {"name": "Produto Parsel", "current_price": "10.00", "url": url},
    )
    monkeypatch.setattr(
        "market_scraper.extraction.extraction_chain.parse_with_beautifulsoup",
        lambda html, url: (_ for _ in ()).throw(AssertionError("bs4 should not run after parsel success")),
    )

    result = ExtractionChain().run(
        "<html><body>produto</body></html>",
        "https://example.com/product",
        "example.com",
        http_status=200,
    )

    assert result.succeeded is True
    assert result.parser_used == "parsel"
    assert [attempt.parser_name for attempt in result.attempts] == ["extruct", "parsel"]


# ── duration_ms e aliases da Fase 5 ──────────────────────────────────────────

def test_extraction_chain_result_has_positive_duration(monkeypatch):
    monkeypatch.setattr(
        "market_scraper.extraction.extraction_chain.parse_with_extruct",
        lambda html, url: {"name": "Produto", "current_price": "99.90", "url": url},
    )

    result = ExtractionChain().run(
        "<html><body>produto</body></html>",
        "https://example.com/p",
        "example.com",
    )

    assert result.duration_ms >= 0
    assert isinstance(result.duration_ms, float)


def test_extraction_result_is_successful_alias(monkeypatch):
    monkeypatch.setattr(
        "market_scraper.extraction.extraction_chain.parse_with_extruct",
        lambda html, url: {"name": "TV", "current_price": "1999.00", "url": url},
    )

    result = ExtractionChain().run("<html></html>", "https://example.com/p", "example.com")

    assert result.is_successful == result.succeeded


def test_extraction_result_first_successful_parser_alias(monkeypatch):
    monkeypatch.setattr(
        "market_scraper.extraction.extraction_chain.parse_with_extruct",
        lambda html, url: {"name": "TV", "current_price": "1999.00", "url": url},
    )

    result = ExtractionChain().run("<html></html>", "https://example.com/p", "example.com")

    assert result.first_successful_parser == result.parser_used


def test_parse_attempt_has_duration_ms(monkeypatch):
    monkeypatch.setattr(
        "market_scraper.extraction.extraction_chain.parse_with_extruct",
        lambda html, url: None,
    )
    monkeypatch.setattr("market_scraper.extraction.extraction_chain.parse_with_parsel", lambda html, url: None)
    monkeypatch.setattr("market_scraper.extraction.extraction_chain.parse_with_beautifulsoup", lambda html, url: None)

    result = ExtractionChain().run("<html></html>", "https://example.com/p", "example.com")

    for attempt in result.attempts:
        assert hasattr(attempt, "duration_ms")
        assert attempt.duration_ms >= 0


def test_extraction_result_is_instance_of_parse_result():
    result = ExtractionChain().run("<html></html>", "https://example.com/p", "example.com")
    assert isinstance(result, ParseResult)
