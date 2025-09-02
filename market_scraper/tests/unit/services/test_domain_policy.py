""" Testes para o módulo de política de domínio """

from market_scraper.services.domain_policy import strategies_for


def test_dominios_semelhantes_nao_sao_correlacionados():
    estrategias = strategies_for("https://fakeamazon.com.br/produto")
    assert estrategias == [] or all("playwright" not in e.__class__.__module__ for e in estrategias)
