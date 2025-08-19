""" Testes da classe ConfigBase garantindo a montagem correta da URL do Redis """

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
