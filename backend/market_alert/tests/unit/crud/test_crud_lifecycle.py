"""Testes de persistência para CRUD de monitorado e concorrente."""

from __future__ import annotations

from market_alert.crud.crud_competitor import create_pending_competitor_product
from market_alert.crud.crud_monitored import create_pending_monitored_product


def test_create_pending_monitored_product_persiste_item(db_session, user) -> None:
    """Cria monitorado pendente e valida consistência dos dados persistidos."""
    created = create_pending_monitored_product(
        db=db_session,
        user_id=user.id,
        name_identification="Notebook Teste",
        product_url="https://loja.com/produto/abc?utm=1",
    )

    assert created.id is not None
    assert created.user_id == user.id
    assert created.normalized_url.startswith("https://loja.com/produto/abc")


def test_create_pending_competitor_product_retorna_existente_sem_duplicar(db_session, monitored) -> None:
    """Garante idempotência do CRUD para a mesma URL concorrente."""
    first = create_pending_competitor_product(
        db=db_session,
        monitored_product_id=monitored.id,
        product_url="https://concorrente.com/produto/1",
        display_name="Concorrente 1",
    )
    second = create_pending_competitor_product(
        db=db_session,
        monitored_product_id=monitored.id,
        product_url="https://concorrente.com/produto/1",
        display_name="Concorrente 1",
    )

    assert first.id == second.id