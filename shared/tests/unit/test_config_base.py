""" Testes da classe ConfigBase garantindo a montagem correta da URL do Redis """

from pathlib import Path
import importlib

import shared.core.config_base as config_base
from shared.core.config_base import ConfigBase

def test_redis_url_with_password():
    settings = ConfigBase(
        REDIS_HOST="host",
        REDIS_PORT=1234,
        REDIS_DB=2,
        REDIS_PASSWORD="segredo",
    )
    assert settings.redis_url == "redis://:segredo@host:1234/2"

def test_redis_url_without_password():
    settings = ConfigBase(
        REDIS_HOST="host",
        REDIS_PORT=1234,
        REDIS_DB=0,
        REDIS_PASSWORD="",
    )
    assert settings.redis_url == "redis://host:1234/0"

def test_service_env_overrides_common(monkeypatch):
    """ Garante que o `.env.<serviço>` sobrescreve variáveis do `.env.common` """
    repo_root = Path(__file__).resolve().parents[3]
    common_file = repo_root / ".env.common"
    service_file = repo_root / ".env.meuservico"

    try:
        common_file.write_text("REDIS_HOST=host_comum\nREDIS_PORT=1111\n")
        service_file.write_text("REDIS_HOST=host_servico\n")

        monkeypatch.setenv("SERVICE_NAME", "meuservico")
        monkeypatch.delenv("REDIS_HOST", raising=False)
        monkeypatch.delenv("REDIS_PORT", raising=False)

        importlib.reload(config_base)
        settings = config_base.ConfigBase()

        assert settings.REDIS_HOST == "host_servico"
        assert settings.REDIS_PORT == 1111
    finally:
        service_file.unlink(missing_ok=True)
        common_file.unlink(missing_ok=True)
        monkeypatch.delenv("SERVICE_NAME", raising=False)
        monkeypatch.delenv("REDIS_HOST", raising=False)
        monkeypatch.delenv("REDIS_PORT", raising=False)
        importlib.reload(config_base)
