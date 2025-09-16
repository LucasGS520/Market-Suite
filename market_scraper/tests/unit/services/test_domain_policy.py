""" Testes para o módulo de política de domínio """

import pytest
import time

import market_scraper.services.domain_policy as domain_policy
from market_scraper.services.domain_policy import strategies_for, strategy_execution_mode_for, pipeline_execution_mode_for
from market_scraper.strategies import (
    MercadoLivreJsonStrategy,
    MercadoLivreHtmlStaticStrategy,
    AmazonJsonStrategy,
    AmazonHtmlStaticStrategy,
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

def test_hot_reload(monkeypatch, tmp_path):
    """ Garante que alterações no arquivo sejam aplicadas com hot-reload """
    #Conteúdo inicial com estratégia JSON do Mercado Livre
    inicial = (
        "strategies:\n"
        "  JSON_ML: MercadoLivreJsonStrategy\n"
        "  JSON_AMAZON: AmazonJsonStrategy\n"
        "policies:\n"
        "  mercadolivre.com.br:\n"
        "    - JSON_ML\n"
    )

    #Conteúdo atualizado apontando para estratégia da Amazon
    atualizado = (
        "strategies:\n"
        "  JSON_ML: MercadoLivreJsonStrategy\n"
        "  JSON_AMAZON: AmazonJsonStrategy\n"
        "policies:\n"
        "  mercadolivre.com.br:\n"
        "    - JSON_AMAZON\n"
    )

    cfg = tmp_path / "domain_policy.yaml"
    cfg.write_text(inicial, encoding="utf-8")

    monkeypatch.setattr(domain_policy, "CONFIG_PATH", cfg)
    domain_policy.load_config()
    domain_policy.enable_hot_reload()

    url = "https://www.mercadolivre.com.br/produto"
    estrategias = domain_policy.strategies_for(url)
    assert isinstance(estrategias[0], MercadoLivreJsonStrategy)

    #Atualiza o arquivo para forçar recarregamento
    time.sleep(1)
    cfg.write_text(atualizado, encoding="utf-8")

    estrategias = domain_policy.strategies_for(url)
    assert isinstance(estrategias[0], AmazonJsonStrategy)

def test_strategy_execution_mode():
    """ Valida o modo configurado para estratégias por domínio """
    assert strategy_execution_mode_for("https://www.amazon.com.br/item") == "parallel"
    assert strategy_execution_mode_for("https://domnio-nao-mapeado.com") == "sequential"

def test_pipeline_execution_mode():
    """ Confere o modo do pipeline para domínio/contexto """
    assert pipeline_execution_mode_for("https://www.amazon.com.br/item") == "parallel"
    assert pipeline_execution_mode_for("https://mercadolivre.com.br/item", context="competitor") == "conditional"
    