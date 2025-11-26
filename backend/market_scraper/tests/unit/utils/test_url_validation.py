""" Testes unitários para utilitário compartilhado de validação de URLs """

from __future__ import annotations

import pytest

from shared.utils.url_validation import UrlIssue, check_url_compatibility, normalize_product_url


def test_normalize_product_url_adiciona_esquema() -> None:
    """Garante que URLs sem esquema recebam ``https`` por padrão"""

    url = normalize_product_url("mercadolivre.com.br/MLB-123")
    assert url.startswith("https://")


def test_normalize_product_url_mantem_host_original() -> None:
    """Confere que o host inicial não é alterado durante a normalização"""

    url = normalize_product_url("https://www.mercadolivre.com.br/MLB-123")
    assert url.startswith("https://www.mercadolivre.com.br")


def test_check_url_compatibility_aceita_urls_basicas() -> None:
    """URLs bem formadas não retornam issues adicionais."""

    issue = check_url_compatibility("https://www.amazon.com.br/dp/B000000001")
    assert issue is None


def test_check_url_compatibility_respeita_validador_publico() -> None:
    """Permite validar host com callback externo quando necessário."""

    def _block_host(host: str) -> UrlIssue | None:
        if host == "www.amazon.com.br":
            return UrlIssue(code="blocked_host", message="Host bloqueado para testes")
        return None

    issue = check_url_compatibility(
        "https://www.amazon.com.br/dp/B000000001",
        ensure_public_endpoint=_block_host,
    )
    assert isinstance(issue, UrlIssue)
    assert issue.code == "blocked_host"


def test_normalize_product_url_rejeita_esquema_invalido() -> None:
    """Esquemas que não utilizam HTTP devem disparar ``ValueError``"""

    with pytest.raises(ValueError):
        normalize_product_url("ftp://www.mercadolivre.com.br/MLB-123")

def test_normalize_product_url_rejeita_credenciais() -> None:
    """URLs com usuário ou senha embutidos devem ser recusadas"""

    with pytest.raises(ValueError):
        normalize_product_url("https://user:senha@www.amazon.com.br/dp/B000000001")


def test_check_url_compatibility_rejeita_credenciais() -> None:
    """Credenciais embutidas geram issue de URL inválida"""

    issue = check_url_compatibility("https://user:senha@www.amazon.com.br/dp/B000000001")
    assert isinstance(issue, UrlIssue)
    assert issue.code == "invalid_url"
        