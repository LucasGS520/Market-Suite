""" Testes para utilitários de preço compartilhados no alert """

from decimal import Decimal

from market_alert.utils.price_utils import normalize_scraped_price, should_create_price_history


def test_normalize_scraped_price_converte_zero_para_none() -> None:
    """Garante que zeros não sejam propagados como preço válido"""

    assert normalize_scraped_price(0) is None
    assert normalize_scraped_price("0.0") is None


def test_should_create_price_history_respeita_indisponibilidade() -> None:
    """Evita criação de histórico quando preço ausente ou indisponível"""

    assert should_create_price_history(None, None) is False
    assert should_create_price_history(Decimal("10.00"), False) is False
    assert should_create_price_history(Decimal("10.00"), True) is True
    