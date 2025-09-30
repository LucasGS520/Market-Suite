""" Testes para o módulo de política de domínio focado no SynergicPipeline """

import os

import pytest

import market_scraper.services.domain_policy as domain_policy
from market_scraper.services.domain_policy import (
    pipeline_steps_for,
    pipeline_execution_mode_for,
    evaluate_feature_flag,
    is_feature_enabled,
    FeatureFlagConfig,
)

def _nomes_das_etapas(etapas: list) -> list[str]:
    """ Extrai os nomes das classes para facilitar asserções legíveis """
    return [etapa.__class__.__name__ for etapa in etapas]

def test_dominios_semelhantes_retorna_lista_vazia():
    """ Domínios parecidos não devem herdar políticas não intencionais """
    etapas = pipeline_steps_for("https://fakeamazon.com.br/produto")
    assert etapas == []


def test_pipeline_steps_padrao_por_dominio():
    """ Verifica se os domínios mapeados recebem etapas na ordem configurada """
    etapas_amazon = _nomes_das_etapas(pipeline_steps_for("https://www.amazon.com.br/produto"))
    assert etapas_amazon[:3] == [
        "ExtructExtractionStep",
        "ParselExtractionStep",
        "BeautifulSoupExtractionStep",
    ]

    etapas_ml = _nomes_das_etapas(pipeline_steps_for("https://www.mercadolivre.com.br/produto"))
    assert etapas_ml[0] == "ExtructExtractionStep"
    assert etapas_ml[-1] == "MechanicalSoupLoginStep"

def test_hot_reload_pipeline(monkeypatch, tmp_path):
    """ Garante que alterações no arquivo sejam aplicadas com hot-reload """
    inicial = (
        "pipeline_steps:\n"
        "  base: SelectorLibExtractionStep\n"
        "pipeline_policies:\n"
        "  mercadolivre.com.br:\n"
        "    - base\n"
    )

    atualizado = (
        "pipeline_steps:\n"
        "  base: ParselExtractionStep\n"
        "pipeline_policies:\n"
        "  mercadolivre.com.br:\n"
        "    - base\n"
    )

    cfg = tmp_path / "domain_policy.yaml"
    cfg.write_text(inicial, encoding="utf-8")

    monkeypatch.setattr(domain_policy, "CONFIG_PATH", cfg)
    domain_policy.load_config()
    domain_policy.enable_hot_reload()

    url = "https://www.mercadolivre.com.br/produto"
    etapas = pipeline_steps_for(url)
    assert _nomes_das_etapas(etapas) == ["SelectorLibExtractionStep"]

    original_mtime = cfg.stat().st_mtime
    cfg.write_text(atualizado, encoding="utf-8")
    os.utime(cfg, (original_mtime, original_mtime))

    etapas = pipeline_steps_for(url)
    assert _nomes_das_etapas(etapas) == ["ParselExtractionStep"]

def test_pipeline_steps_ignora_classes_inexistentes(monkeypatch, tmp_path):
    """ Classes inexistentes no YAML devem ser descartadas silenciosamente """
    config = (
        "pipeline_steps:\n"
        "  inexistente: ClasseQueNaoExiste\n"
        "pipeline_policies:\n"
        "  example.com:\n"
        "    - inexistente\n"
    )

    cfg = tmp_path / "domain_policy.yaml"
    cfg.write_text(config, encoding="utf-8")

    monkeypatch.setattr(domain_policy, "CONFIG_PATH", cfg)
    domain_policy.load_config()

    etapas = pipeline_steps_for("https://example.com/produto")
    assert etapas == []

def test_pipeline_step_options_aplica_timeout(monkeypatch, tmp_path):
    """ Opções declaradas na política devem ajustar argumentos das etapas """
    config = (
        "pipeline_steps:\n"
        "  extruct:\n"
        "    class: ExtructExtractionStep\n"
        "    default_options:\n"
        "      timeout: 5\n"
        "pipeline_policies:\n"
        "  example.com:\n"
        "    - extruct\n"
        "pipeline_step_options:\n"
        "  example.com:\n"
        "    default:\n"
        "      extruct:\n"
        "        timeout: 9\n"
    )

    cfg = tmp_path / "domain_policy.yaml"
    cfg.write_text(config, encoding="utf-8")

    monkeypatch.setattr(domain_policy, "CONFIG_PATH", cfg)
    domain_policy.load_config()

    etapas = pipeline_steps_for("https://example.com/produto")
    assert len(etapas) == 1
    etapa = etapas[0]
    assert etapa.__class__.__name__ == "ExtructExtractionStep"
    assert getattr(etapa, "timeout") == 9.0

def test_pipeline_execution_mode():
    """ Confere o modo do pipeline para domínio/contexto """
    assert pipeline_execution_mode_for("https://www.amazon.com.br/item") == "parallel"
    assert (
        pipeline_execution_mode_for("https://mercadolivre.com.br/item", context="competitor")
        == "conditional"
    )
    
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
    