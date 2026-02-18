""" Testes unitários para o fluxo transacional de persistência do monitorado. """

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from types import SimpleNamespace
from uuid import uuid4

from market_alert.crud import crud_monitored
from market_alert.enums.enums_products import MonitoredStatus, MonitoringType
from market_alert.models.models_products import MonitoredProduct
from shared.schemas.shared_schemas_products import (
    MonitoredProductCreateScraping,
    MonitoredScrapedInfo,
)


def _configurar_janelas_deterministicas(monkeypatch) -> None:
    """ Força janelas fixas para tornar os asserts de agendamento determinísticos. """
    monkeypatch.setattr(crud_monitored.settings, "COLLECT_INTERVAL_UNSTABLE_MIN", 300)
    monkeypatch.setattr(crud_monitored.settings, "COLLECT_INTERVAL_UNSTABLE_MAX", 300)
    monkeypatch.setattr(crud_monitored.settings, "COLLECT_INTERVAL_STABLE_MIN", 900)
    monkeypatch.setattr(crud_monitored.settings, "COLLECT_INTERVAL_STABLE_MAX", 900)
    monkeypatch.setattr(crud_monitored.settings, "COLLECT_INTERVAL_VERY_STABLE_MIN", 1800)
    monkeypatch.setattr(crud_monitored.settings, "COLLECT_INTERVAL_VERY_STABLE_MAX", 1800)
    monkeypatch.setattr(crud_monitored.settings, "STABILITY_DAYS_STABLE", 3)
    monkeypatch.setattr(crud_monitored.settings, "STABILITY_DAYS_VERY_STABLE", 7)


def _build_existing_monitored(*, price: str, last_change_at: datetime) -> MonitoredProduct:
    """ Monta um monitorado em memória para validar regras sem acesso ao banco real. """
    monitored = MonitoredProduct(
        id=uuid4(),
        user_id=uuid4(),
        name_identification="Produto teste",
        monitoring_type=MonitoringType.scraping,
        product_url="https://loja.example/produto-1",
        normalized_url="https://loja.example/produto-1",
        status=MonitoredStatus.active,
        current_price=Decimal(price),
        currency="BRL",
    )
    monitored.last_price_change_at = last_change_at
    monitored.last_scraped_at = last_change_at
    return monitored


def _build_inputs(price: str) -> tuple[MonitoredProductCreateScraping, MonitoredScrapedInfo]:
    """ Centraliza payload mínimo usado pelos cenários de atualização. """
    product_data = MonitoredProductCreateScraping(
        name_identification="Produto teste",
        product_url="https://loja.example/produto-1",
    )
    scraped_info = MonitoredScrapedInfo(
        product_url="https://loja.example/produto-1",
        name="Produto teste",
        current_price=Decimal(price),
        currency="BRL",
        availability=True,
        last_status="available",
        thumbnail=None,
        free_shipping=False,
    )
    return product_data, scraped_info


def test_sem_mudanca_de_preco_mantem_ou_evolui_estabilidade(monkeypatch) -> None:
    """ Sem alteração de preço a estabilidade evolui e usa janela mais longa. """
    _configurar_janelas_deterministicas(monkeypatch)

    now = datetime.now(timezone.utc).replace(microsecond=0)
    existing = _build_existing_monitored(price="100.00", last_change_at=now - timedelta(days=8))
    product_data, scraped_info = _build_inputs("100.00")
    fake_db = SimpleNamespace(commit=lambda: None, rollback=lambda: None, refresh=lambda _: None)

    monkeypatch.setattr(crud_monitored, "get_monitored_product_by_user_and_url", lambda *_: existing)

    updated = crud_monitored.create_or_update_monitored_product_scraped(
        fake_db,
        existing.user_id,
        product_data,
        scraped_info,
        now,
    )

    assert updated.stability_score == crud_monitored.calculate_stability_score(updated, reference_time=now)
    assert updated.stability_score == 2
    assert updated.next_check_at == now + timedelta(seconds=1800)


def test_com_mudanca_de_preco_reseta_para_instavel_e_janela_curta(monkeypatch) -> None:
    """ Mudança de preço reseta estabilidade no mesmo ciclo e agenda retry curto. """
    _configurar_janelas_deterministicas(monkeypatch)

    now = datetime.now(timezone.utc).replace(microsecond=0)
    existing = _build_existing_monitored(price="100.00", last_change_at=now - timedelta(days=10))
    product_data, scraped_info = _build_inputs("120.00")
    fake_db = SimpleNamespace(commit=lambda: None, rollback=lambda: None, refresh=lambda _: None)

    monkeypatch.setattr(crud_monitored, "get_monitored_product_by_user_and_url", lambda *_: existing)
    monkeypatch.setattr(crud_monitored.crud_price_history, "create_for_monitored", lambda *args, **kwargs: None)

    updated = crud_monitored.create_or_update_monitored_product_scraped(
        fake_db,
        existing.user_id,
        product_data,
        scraped_info,
        now,
    )

    assert updated.stability_score == crud_monitored.STABILITY_UNSTABLE
    assert updated.last_price_change_at == now
    assert updated.next_check_at == now + timedelta(seconds=300)


def test_next_check_at_considera_nova_estabilidade_no_mesmo_ciclo(monkeypatch) -> None:
    """ Garante que o agendamento enxerga stability_score já recalculada. """
    _configurar_janelas_deterministicas(monkeypatch)

    now = datetime.now(timezone.utc).replace(microsecond=0)
    existing = _build_existing_monitored(price="100.00", last_change_at=now - timedelta(days=10))
    product_data, scraped_info = _build_inputs("130.00")
    fake_db = SimpleNamespace(commit=lambda: None, rollback=lambda: None, refresh=lambda _: None)

    stability_seen: list[int | None] = []

    def _calculate_next_check_spy(product, collected_at):
        #Registramos o score observado para provar que o cálculo acontece após o recálculo.
        stability_seen.append(product.stability_score)
        return collected_at + timedelta(seconds=300)

    monkeypatch.setattr(crud_monitored, "get_monitored_product_by_user_and_url", lambda *_: existing)
    monkeypatch.setattr(crud_monitored, "calculate_next_check_at", _calculate_next_check_spy)
    monkeypatch.setattr(crud_monitored.crud_price_history, "create_for_monitored", lambda *args, **kwargs: None)

    crud_monitored.create_or_update_monitored_product_scraped(
        fake_db,
        existing.user_id,
        product_data,
        scraped_info,
        now,
    )

    assert stability_seen == [crud_monitored.STABILITY_UNSTABLE]
    