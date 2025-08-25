""" Testes para utilitários de cache HTTP """

import logging
import pytest

from shared.utils import redis_client
from market_scraper.utils.http_cache import store_cache_headers, get_cache_headers, ContentSignature, NOT_MODIFIED


def test_store_and_retrieve_headers(fake_redis):
    url = "https://example.com/produto"
    store_cache_headers(
        url, etag="etag123", last_modified="Mon, 01 Jan 2024 00:00:00 GMT"
    )
    headers = get_cache_headers(url)
    assert headers["etag"] == "etag123"
    assert headers["last_modified"] == "Mon, 01 Jan 2024 00:00:00 GMT"

def test_content_signature_detection(fake_redis):
    url = "https://example.com/produto"
    html_a = "<html>A</html>"
    html_b = "<html>B</html>"

    signer = ContentSignature(url)

    assert signer.has_changed(html_a) is True
    assert signer.has_changed(html_a) is False
    assert signer.has_changed(html_b) is True
    assert signer.get() == signer.calculate(html_b)

def test_check_or_update(fake_redis):
    """ Valida comportamento da verificação e atualização condicional """
    url = "https://example.com/produto"
    html_a = "<html>A</html>"
    html_b = "<html>B</html>"

    signer = ContentSignature(url)

    primeira_assinatura = signer.check_or_update(html_a)
    assert primeira_assinatura == signer.calculate(html_a)

    #Conteudo igual deve retornar a sentinela NOT_MODIFIED
    assert signer.check_or_update(html_a) is NOT_MODIFIED

    #Conteudo diferente deve gerar nova assinatura
    nova_assinatura = signer.check_or_update(html_b)
    assert nova_assinatura == signer.calculate(html_b)
    assert signer.get() == nova_assinatura

def test_cache_headers_expiration(fake_redis):
    url = "https://example.com/expira"
    store_cache_headers(
        url,
        etag="e1",
        last_modified="Mon, 01 Jan 2024 00:00:00 GMT",
        ttl_seconds=60,
    )
    fake_redis.advance_time(61)
    headers = get_cache_headers(url)
    assert headers["etag"] is None
    assert headers["last_modified"] is None

def test_store_cache_headers_logs_error(monkeypatch, caplog):
    class FailingRedis:
        def set(self, *a, **k):
            raise Exception("falha")

    monkeypatch.setattr(redis_client, "get_redis_client", lambda: FailingRedis())
    with caplog.at_level(logging.ERROR):
        store_cache_headers("https://erro.com", etag="e")
    assert "Falha ao armazenar cabeçalhos de cache no Redis" in caplog.text

def test_get_cache_headers_logs_error(monkeypatch, caplog):
    class FailingRedis:
        def get(self, *a, **k):
            raise Exception("falha")

    monkeypatch.setattr(redis_client, "get_redis_client", lambda: FailingRedis())
    with caplog.at_level(logging.ERROR):
        headers = get_cache_headers("https://erro.com")
    assert headers == {"etag": None, "last_modified": None}
    assert "Falha ao recuperar cabeçalhos de cache no Redis" in caplog.text

def test_content_signature_logs_error(monkeypatch, caplog):
    class FailingRedis:
        def get(self, *a, **k):
            raise Exception("falha")

        def set(self, *a, **k):
            raise Exception("falha")

    monkeypatch.setattr(redis_client, "get_redis_client", lambda: FailingRedis())

    signer = ContentSignature("https://erro.com")
    with caplog.at_level(logging.ERROR):
        assert signer.get() is None
        signer.update("<html></html>")
        assert signer.has_changed("<html></html>") is True
        signer.check_or_update("<html></html>")

    #Verifica que todas as etapas registram mensagens de erro
    text = caplog.text
    assert "Erro ao obter assinatura de conteúdo no Redis" in text
    assert "Erro ao atualizar assinatura de conteúdo no Redis" in text
    assert "Erro ao verificar assinatura de conteúdo no Redis" in text
    assert "Erro ao verificar/atualizar assinatura de conteúdo no Redis" in text
