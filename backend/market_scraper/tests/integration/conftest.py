from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from market_scraper.main import app


INTEGRATION_DIR = Path(__file__).resolve().parent
FIXTURES_DIR = INTEGRATION_DIR.parent / "fixtures"


@pytest.fixture
def integration_client():
    with TestClient(app) as client:
        yield client


@pytest.fixture
def fixture_html_loader():
    def _load(name: str) -> str:
        return (FIXTURES_DIR / name).read_text(encoding="utf-8")

    return _load


@pytest.fixture
def success_product_html(fixture_html_loader) -> str:
    return fixture_html_loader("product_success.html")


@pytest.fixture
def js_challenge_html(fixture_html_loader) -> str:
    return fixture_html_loader("response_js_challenge.html")
