""" Testes para o módulo de política de domínio """

from market_scraper.services.domain_policy import strategies_for
from market_scraper.strategies.playwright_default import PlaywrightDefaultStrategy


def test_dominios_semelhantes_nao_sao_correlacionados():
    estrategias = strategies_for("https://fakeamazon.com.br/produto")
    assert estrategias == []
