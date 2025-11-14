""" Testes das rotas responsáveis por scraping de concorrentes """

from decimal import Decimal
from uuid import uuid4

from fastapi import HTTPException, status

from market_alert.enums.enums_products import MonitoringType, MonitoredStatus, ProductStatus
from market_alert.models.models_products import MonitoredProduct, CompetitorProduct
from market_alert.models.models_users import User
from market_alert.core.password import hash_password


def test_create_competitor_scrape_autorizado_agenda_task(
    client,
    db_session,
    test_user,
    prepare_test_database,
    monkeypatch,
):
    """ Garante que o agendamento ocorra quando o produto pertence ao usuário autenticado """

    monitored = MonitoredProduct(
        user_id=test_user.id,
        name_identification="Notebook Gamer",
        monitoring_type=MonitoringType.scraping,
        product_url="https://example.com/produto-monitorado",
        status=MonitoredStatus.active,
    )
    db_session.add(monitored)
    db_session.commit()

    captured = {}

    def fake_delay(*args, **kwargs):
        """ Captura os argumentos enviados para o Celery sem executar a task """

        captured["args"] = args
        captured["kwargs"] = kwargs

    monkeypatch.setattr(
        "market_alert.routes.routes_competitors.collect_competitor_task.delay",
        fake_delay,
    )

    monkeypatch.setattr(
        "market_alert.routes.routes_competitors._enforce_competitor_scrape_rate_limit",
        lambda _user_id: None,
    )

    response = client.post(
        "/competitors/scrape",
        json={
            "monitored_product_id": str(monitored.id),
            "product_url": "https://www.mercadolivre.com.br/MLB-123",
        },
    )

    assert response.status_code == 202
    assert captured["kwargs"] == {
        "monitored_product_id": str(monitored.id),
        "url": "https://www.mercadolivre.com.br/MLB-123",
    }


def test_create_competitor_scrape_usuario_diferente_recebe_erro(
    client,
    db_session,
    prepare_test_database,
    monkeypatch,
):
    """ Assegura que a rota negue acesso quando o monitorado pertence a outro usuário """
    unique_suffix = uuid4().hex[:8]
    outro_user = User(
        id=uuid4(),
        name="Outro Usuário",
        email=f"outro_{unique_suffix}@example.com",
        phone_number=f"119{unique_suffix}",
        password=hash_password("senha123"),
    )
    db_session.add(outro_user)
    db_session.flush()

    monitored = MonitoredProduct(
        user_id=outro_user.id,
        name_identification="Monitor Ultrawide",
        monitoring_type=MonitoringType.scraping,
        product_url="https://example.com/produto-ultrawide",
        status=MonitoredStatus.active,
    )
    db_session.add(monitored)
    db_session.commit()

    called = {"count": 0}

    def fake_delay(*args, **kwargs):
        """ Indica que a task não deveria ser executada quando não autorizado """

        called["count"] += 1

    monkeypatch.setattr(
        "market_alert.routes.routes_competitors.collect_competitor_task.delay",
        fake_delay,
    )

    response = client.post(
        "/competitors/scrape",
        json={
            "monitored_product_id": str(monitored.id),
            "product_url": "https://www.mercadolivre.com.br/MLB-123",
        },
    )

    assert response.status_code == 403
    assert response.json()["detail"] == "Usuário não possui permissão para acessar este produto monitorado."
    assert called["count"] == 0
    
def test_create_competitor_scrape_respects_rate_limit(
    client,
    db_session,
    test_user,
    prepare_test_database,
    monkeypatch,
):
    """Confere que o endpoint devolve 429 quando o limite configurado é excedido"""

    monitored = MonitoredProduct(
        user_id=test_user.id,
        name_identification="Monitor 4K",
        monitoring_type=MonitoringType.scraping,
        product_url="https://example.com/produto-monitorado",
        status=MonitoredStatus.active,
    )
    db_session.add(monitored)
    db_session.commit()

    called = {"count": 0}

    def fake_delay(*args, **kwargs):
        """Impede que a task seja agendada quando o rate limit bloqueia a requisição"""

        called["count"] += 1

    def fake_rate_limit(_user_id):
        """Simula estouro de limite diário para validar retorno HTTP"""

        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Limite de scraping de concorrentes atingido. Tente novamente em instantes.",
        )

    monkeypatch.setattr(
        "market_alert.routes.routes_competitors.collect_competitor_task.delay",
        fake_delay,
    )
    monkeypatch.setattr(
        "market_alert.routes.routes_competitors._enforce_competitor_scrape_rate_limit",
        fake_rate_limit,
    )

    response = client.post(
        "/competitors/scrape",
        json={
            "monitored_product_id": str(monitored.id),
            "product_url": "https://www.mercadolivre.com.br/MLB-123",
        },
    )

    assert response.status_code == 429
    assert response.json()["detail"] == "Limite de scraping de concorrentes atingido. Tente novamente em instantes."
    assert called["count"] == 0

def test_list_competitors_returns_paginated_items(
    client,
    db_session,
    test_user,
    prepare_test_database,
):
    """Garante que a listagem retorne paginação e campos do contrato card-first"""

    monitored = MonitoredProduct(
        user_id=test_user.id,
        name_identification="Smartphone X",
        monitoring_type=MonitoringType.scraping,
        product_url="https://example.com/smartphone",
        status=MonitoredStatus.active,
    )
    db_session.add(monitored)
    db_session.flush()

    competitors = [
        CompetitorProduct(
            monitored_product_id=monitored.id,
            name_competitor=f"Loja {index}",
            product_url=f"https://example.com/concorrente-{index}",
            current_price=Decimal(100 + index),
            old_price=Decimal(110 + index),
            status=ProductStatus.available,
        )
        for index in range(3)
    ]
    db_session.add_all(competitors)
    db_session.commit()

    response = client.get(
        f"/competitors?monitored_id={monitored.id}&per_page=2&page=1&include_paused=true",
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] == 3
    assert payload["page"] == 1
    assert payload["per_page"] == 2
    assert len(payload["items"]) == 2

    first_item = payload["items"][0]
    assert set(first_item.keys()) == {
        "id",
        "monitored_product_id",
        "name",
        "product_url",
        "current_price",
        "previous_price",
        "price_change",
        "price_change_percentage",
        "status",
        "last_checked",
        "is_paused",
    }
    assert first_item["monitored_product_id"] == str(monitored.id)

def test_bulk_pause_competitors_marks_entries_as_paused(
    client,
    db_session,
    test_user,
    prepare_test_database,
):
    """Certifica que a rota de pausa em massa marca cada concorrente como pausado"""

    monitored = MonitoredProduct(
        user_id=test_user.id,
        name_identification="Headset Gamer",
        monitoring_type=MonitoringType.scraping,
        product_url="https://example.com/headset",
        status=MonitoredStatus.active,
    )
    db_session.add(monitored)
    db_session.flush()

    competitors = [
        CompetitorProduct(
            monitored_product_id=monitored.id,
            name_competitor=f"Loja Teste {index}",
            product_url=f"https://example.com/loja-{index}",
            current_price=Decimal("50.00"),
            old_price=Decimal("55.00"),
            status=ProductStatus.available,
        )
        for index in range(2)
    ]
    db_session.add_all(competitors)
    db_session.flush()

    monitored_id = monitored.id
    competitor_ids = [item.id for item in competitors]
    db_session.commit()

    payload = {
        "monitored_product_id": str(monitored_id),
        "competitor_ids": [str(item_id) for item_id in competitor_ids],
    }
    response = client.post("/competitors/bulk/pause", json=payload)

    assert response.status_code == 200
    reloaded = [db_session.get(CompetitorProduct, item.id) for item in competitors]
    assert all(item.is_paused is True for item in reloaded)

def test_bulk_pause_and_resume_competitors(
    client,
    db_session,
    test_user,
    prepare_test_database,
):
    """Valida que ações em massa respeitam ownership e atualizam a flag is_paused"""

    monitored = MonitoredProduct(
        user_id=test_user.id,
        name_identification="Console Gamer",
        monitoring_type=MonitoringType.scraping,
        product_url="https://example.com/console",
        status=MonitoredStatus.active,
    )
    db_session.add(monitored)
    db_session.flush()

    competitor_a = CompetitorProduct(
        monitored_product_id=monitored.id,
        name_competitor="Loja A",
        product_url="https://example.com/loja-a",
        current_price=Decimal('90.00'),
        old_price=Decimal('95.00'),
        status=ProductStatus.available,
    )
    competitor_b = CompetitorProduct(
        monitored_product_id=monitored.id,
        name_competitor="Loja B",
        product_url="https://example.com/loja-b",
        current_price=Decimal('120.00'),
        old_price=Decimal('110.00'),
        status=ProductStatus.available,
    )
    db_session.add_all([competitor_a, competitor_b])
    db_session.flush()

    monitored_id = monitored.id
    competitor_a_id = competitor_a.id
    competitor_b_id = competitor_b.id
    db_session.commit()

    pause_response = client.post(
        "/competitors/bulk/pause",
        json={
            "monitored_product_id": str(monitored_id),
            "competitor_ids": [str(competitor_a_id), str(competitor_b_id)],
        },
    )

    assert pause_response.status_code == 200
    competitor_a = db_session.get(CompetitorProduct, competitor_a_id)
    competitor_b = db_session.get(CompetitorProduct, competitor_b_id)
    assert competitor_a.is_paused is True
    assert competitor_b.is_paused is True

    resume_response = client.post(
        "/competitors/bulk/resume",
        json={
            "monitored_product_id": str(monitored_id),
            "competitor_ids": [str(competitor_a_id)],
        },
    )

    assert resume_response.status_code == 200
    competitor_a = db_session.get(CompetitorProduct, competitor_a_id)
    competitor_b = db_session.get(CompetitorProduct, competitor_b_id)
    assert competitor_a.is_paused is False
    assert competitor_b.is_paused is True

    remove_response = client.post(
        "/competitors/bulk/remove",
        json={
            "monitored_product_id": str(monitored_id),
            "competitor_ids": [str(competitor_b_id)],
        },
    )

    assert remove_response.status_code == 200
    remaining = db_session.query(CompetitorProduct).filter_by(monitored_product_id=monitored_id).all()
    assert len(remaining) == 1
    assert remaining[0].id == competitor_a_id