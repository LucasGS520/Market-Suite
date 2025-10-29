""" Testes unitários para utilitário compartilhado de validação de URLs """

from __future__ import annotations

import pytest

from shared.utils.url_validation import (
    UrlIssue,
    check_url_compatibility,
    normalize_product_url,
)


def test_normalize_product_url_adiciona_esquema() -> None:
    """Garante que URLs sem esquema recebam ``https`` por padrão"""

    url = normalize_product_url("mercadolivre.com.br/MLB-123")
    assert url.startswith("https://")


def test_normalize_product_url_mantem_host_original() -> None:
    """Confere que o host inicial não é alterado durante a normalização"""

    url = normalize_product_url("https://www.mercadolivre.com.br/MLB-123")
    assert url.startswith("https://www.mercadolivre.com.br")


def test_check_url_compatibility_rejeita_dominios_nao_suportados() -> None:
    """Rejeita marketplaces fora da lista de domínios suportados"""

    issue = check_url_compatibility("https://loja.inexistente.com/produto")
    assert isinstance(issue, UrlIssue)
    assert issue.code == "unsupported_marketplace"


def test_check_url_compatibility_rejeita_paginas_nao_produto() -> None:
    """URLs válidas porém sem padrão de produto devem falhar"""

    issue = check_url_compatibility("https://www.amazon.com.br/ofertas")
    assert isinstance(issue, UrlIssue)
    assert issue.code == "not_a_product"


def test_check_url_compatibility_aceita_produto_valido() -> None:
    """Domínios suportados com caminho de produto devem ser aceitos"""

    issue = check_url_compatibility("https://www.amazon.com.br/dp/B000000001")
    assert issue is None


def test_check_url_compatibility_respeita_validador_publico() -> None:
    """Permite sobrepor validação de host para reforçar mitigação de SSRF"""

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
        