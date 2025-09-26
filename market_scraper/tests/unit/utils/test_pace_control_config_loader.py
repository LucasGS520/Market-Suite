""" Testes focados no carregamento das políticas de pace control via YAML """

from __future__ import annotations

from market_scraper.utils_controllers.configuration.pace_control_config import (
    PaceControlPolicy,
    settings,
)


def test_settings_policy_for_carrega_yaml_sem_erros() -> None:
    """ Garante que a política carregada para domínio conhecido reflita o YAML """
    policy = settings.policy_for("mercadolivre.com.br")

    assert isinstance(policy, PaceControlPolicy)
    assert policy.rate_limit is not None
    assert policy.rate_limit.max_requests == 120
    assert policy.rate_limit.window == 60
