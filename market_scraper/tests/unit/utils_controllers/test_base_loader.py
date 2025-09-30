""" Testes do utilitário de carregamento genérico de configurações """

from __future__ import annotations

import os
from pathlib import Path

import pytest

from market_scraper.utils_controllers.configuration.base_loader import (
    HotReloadSettingsStore,
    load_yaml_file,
    parse_env_flag,
    resolve_config_path,
)


def test_parse_env_flag_normaliza_textos() -> None:
    """ Garante que valores textuais são corretamente convertidos para booleanos """
    assert parse_env_flag("1")
    assert parse_env_flag("true")
    assert not parse_env_flag("0")
    assert not parse_env_flag(None)

def test_resolve_config_path_respeita_variavel(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """ Confirma que o caminho padrão é sobrescrito via variável de ambiente """
    default_path = tmp_path / "default.yaml"
    override_path = tmp_path / "override.yaml"
    monkeypatch.setenv("TEST_CONFIG_OVERRIDE", str(override_path))

    resolved = resolve_config_path(default_path, env_var="TEST_CONFIG_OVERRIDE")
    assert resolved == override_path

    monkeypatch.delenv("TEST_CONFIG_OVERRIDE", str(override_path))
    assert resolved == override_path

    monkeypatch.delenv("TEST_CONFIG_OVERRIDE", raising=False)
    resolved_default = resolve_config_path(default_path, env_var="TEST_CONFIG_OVERRIDE")
    assert resolved_default == default_path

def test_load_yaml_file_lida_com_cache(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """ Verifica que a leitura de arquivo inexistente retorna dicionário vazio """
    missing = tmp_path / "missing.yaml"
    assert load_yaml_file(missing) == {}

    content = tmp_path / "content.yaml"
    content.write_text("chave: valor\n", encoding="utf-8")
    assert load_yaml_file(content) == {"chave": "valor"}

def test_hot_reload_settings_store_com_cache(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """ Avalia comportamento de cache e hot-reload do ``HotReloadSettingsStore`` """
    config_file = tmp_path / "config.yaml"
    config_file.write_text("valor: 1\n", encoding="utf-8")

    store = HotReloadSettingsStore[
        dict
    ](
        default_path=config_file,
        env_var=None,
        hot_reload_env="TEST_HOT_RELOAD",
        builder=lambda data: data,
    )

    first = store.get()
    assert first["valor"] == 1

    config_file.write_text("valor: 2\n", encoding="utf-8")
    cached = store.get()
    assert cached["valor"] == 1

    refreshed = store.reload()
    assert refreshed["valor"] == 2

    original_mtime = config_file.stat().st_mtime
    monkeypatch.setenv("TEST_HOT_RELOAD", "1")
    config_file.write_text("valor: 3\n", encoding="utf-8")
    os.utime(config_file, (original_mtime, original_mtime))

    updated = store.get()
    assert updated["valor"] == 3
