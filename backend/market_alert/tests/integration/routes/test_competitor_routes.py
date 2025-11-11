""" Testes das rotas responsáveis por scraping de concorrentes """

from uuid import uuid4

from market_alert.enums.enums_products import MonitoringType, MonitoredStatus
from market_alert.models.models_products import MonitoredProduct
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
    