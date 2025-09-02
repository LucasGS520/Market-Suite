""" Testes para o módulo de política de domínio """

import pytest

from market_scraper.services.domain_policy import strategies_for
from market_scraper.strategies import (
    MercadoLivreJsonStrategy,
    MercadoLivreHtmlStaticStrategy,
    AmazonJsonStrategy,
    AmazonHtmlStaticStrategy,
    ShopeeJsonStrategy,
    ShopeeHtmlStaticStrategy,
    MagaluJsonStrategy,
    MagaluHtmlStaticStrategy,
)

def test_dominios_semelhantes_nao_sao_correlacionados():
    """ Domínios parecidos não devem ser tratados como equivalentes """
    estrategias = strategies_for("https://fakeamazon.com.br/produto")
    assert estrategias == [] or all(
        "playwright" not in e.__class__.__module__ for e in estrategias
    )

@pytest.mark.parametrize(
    "url, esperadas",
    [
        (
            "https://www.mercadolivre.com.br/produto",
            [MercadoLivreJsonStrategy(), MercadoLivreHtmlStaticStrategy()],
        ),
        (
            "https://www.amazon.com.br/produto",
            [AmazonJsonStrategy(), AmazonHtmlStaticStrategy()],
        ),
        (
            "https://www.shopee.com.br/produto",
            [ShopeeJsonStrategy(), ShopeeHtmlStaticStrategy()],
        ),
        (
            "https://www.magazineluiza.com.br/produto",
            [MagaluJsonStrategy(), MagaluHtmlStaticStrategy()],
        ),
    ],
)
def test_ordem_estrategias_json_html_sem_playwright(url, esperadas):
    """ Verifica a ordem JSON -> HTML e ausência de Playwright para cada domínio """
    estrategias = strategies_for(url)

    #Assegura que estratégias Playwright não estejam presentes
    assert all("playwright" not in e.__class__.__module__ for e in estrategias)

    #Confere se a sequência corresponde às classes esperadas
    assert len(estrategias) == len(esperadas)
    for retornada, esperada in zip(estrategias, esperadas):
        assert isinstance(retornada, type(esperada))
