""" Testes para o módulo de política de domínio """

import pytest
import time

import market_scraper.services.domain_policy as domain_policy
from market_scraper.services.domain_policy import (
    strategies_for, 
    strategy_execution_mode_for, 
    pipeline_execution_mode_for, 
    rate_limit_policy_for,
    evaluate_feature_flag,
    is_feature_enabled,
    FeatureFlagConfig,
)
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
    """ Valida o modo configurado para estratégias por domínio/contexto """
    assert strategy_execution_mode_for("https://www.amazon.com.br/item") == "parallel"
    assert strategy_execution_mode_for("https://www.mercadolivre.com.br/item", context="competitor") == "sequential"
    assert strategy_execution_mode_for("https://dominio-nao-mapeado.com", context="competitor") == "sequential"

def test_pipeline_execution_mode():
    """ Confere o modo do pipeline para domínio/contexto """
    assert pipeline_execution_mode_for("https://www.amazon.com.br/item") == "parallel"
    assert pipeline_execution_mode_for("https://mercadolivre.com.br/item", context="competitor") == "conditional"
    
def test_contexto_competitor_prioriza_html():
    """ Contextos específicos podem alterar a lista de estratégias """
    url = "https://www.mercadolivre.com.br/produto"
    padrao = strategies_for(url)
    competitor = strategies_for(url, context="competitor")

    assert any(isinstance(e, MercadoLivreJsonStrategy) for e in padrao)
    assert all(not isinstance(e, MercadoLivreJsonStrategy) for e in competitor)

def test_rate_limit_policy_for_domain():
    """ Deve retornar configuração específica de rate limit por domínio """
    policy = rate_limit_policy_for("https://www.amazon.com.br/produto")
    assert policy is not None
    assert policy["max_requests"] > 0
    assert policy["window"] > 0

def test_rate_limit_policy_default():
    """ Domínios não mapeados utilizam configuração padrão quando disponível """
    default = rate_limit_policy_for("https://domnio-nao-mapeado.com/item")
    assert default is not None
    assert default["max_requests"] > 0
    
def test_feature_flag_default_enabled(monkeypatch):
    """ Quando a feature flag não está configurada deve respeitar o valor padrão """
    monkeypatch.setattr(domain_policy, "_reload_if_needed", lambda: None)
    monkeypatch.setattr(domain_policy, "FEATURE_FLAGS", {})

    decision = evaluate_feature_flag(
        "synergic_pipeline",
        "https://site-novo.com/produto",
        identifier="usuario-1",
    )

    assert decision.enabled is True
    assert decision.configured is False
    assert decision.rollout_percentage == 100.0

def test_feature_flag_rollout_percentage(monkeypatch):
    """ Deve respeitar rollout percentual e produzir decisão determinística """
    monkeypatch.setattr(domain_policy, "_reload_if_needed", lambda: None)
    monkeypatch.setattr(
        domain_policy,
        "FEATURE_FLAGS",
        {
            "synergic_pipeline": {
                "mercadolivre.com.br": {
                    "default": FeatureFlagConfig(enabled=True, rollout_percentage=30.0)
                },
                "default": {
                    "default": FeatureFlagConfig(enabled=True, rollout_percentage=50.0)
                },
            }
        },
    )

    monkeypatch.setattr(domain_policy, "_compute_rollout_bucket", lambda identifier: 25.0)

    decision = evaluate_feature_flag(
        "synergic_pipeline",
        "https://www.mercadolivre.com.br/produto",
        identifier="usuario-canario",
    )

    assert decision.enabled is True
    assert decision.bucket_value == 25.0
    assert decision.rollout_percentage == 30.0

    monkeypatch.setattr(domain_policy, "_compute_rollout_bucket", lambda identifier: 80.0)
    decision_negado = evaluate_feature_flag(
        "synergic_pipeline",
        "https://www.mercadolivre.com.br/produto",
        identifier="usuario-canario",
    )

    assert decision_negado.enabled is False
    assert decision_negado.rollout_percentage == 30.0

def test_feature_flag_disabled(monkeypatch):
    """ Configurações com enabled=False devem bloquear a funcionaliade """
    monkeypatch.setattr(domain_policy, "_reload_if_needed", lambda: None)
    monkeypatch.setattr(
        domain_policy,
        "FEATURE_FLAGS",
        {
            "synergic_pipeline": {
                "example.com": {
                    "default": FeatureFlagConfig(enabled=False, rollout_percentage=100.0)
                }
            }
        },
    )

    ativo = is_feature_enabled(
        "synergic_pipeline",
        "https://sub.example.com/produto",
        identifier="usuario",
    )

    assert ativo is False
    