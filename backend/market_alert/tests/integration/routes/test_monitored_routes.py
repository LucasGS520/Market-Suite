""" Testes das rotas de produtos monitorados """

from decimal import Decimal

from market_alert.enums.enums_products import MonitoringType, MonitoredStatus, ProductStatus
from market_alert.models.models_products import MonitoredProduct, CompetitorProduct
from market_alert.tasks import scraper_tasks


def test_list_monitored_products_inclui_contagem_concorrentes(client, db_session, test_user, prepare_test_database):
    """ Garante que a rota retorne a quantidade de concorrentes por produto monitorado """
    monitored = MonitoredProduct(
        user_id=test_user.id,
        name_identification="Notebook Gamer",
        monitoring_type=MonitoringType.scraping,
        product_url="https://example.com/produto-1",
        current_price=Decimal("4200.00"),
        status=MonitoredStatus.active,
    )
    db_session.add(monitored)
    db_session.flush()

    competitor_a = CompetitorProduct(
        monitored_product_id=monitored.id,
        name_competitor="Loja A",
        product_url="https://example.com/concorrente-a",
        current_price=Decimal("4100.00"),
        status=ProductStatus.available,
    )
    competitor_b = CompetitorProduct(
        monitored_product_id=monitored.id,
        name_competitor="Loja B",
        product_url="https://example.com/concorrente-b",
        current_price=Decimal("4150.00"),
        status=ProductStatus.available,
    )
    db_session.add_all([competitor_a, competitor_b])

    outro_monitorado = MonitoredProduct(
        user_id=test_user.id,
        name_identification="Monitor Ultrawide",
        monitoring_type=MonitoringType.scraping,
        product_url="https://example.com/produto-2",
        current_price=Decimal("2550.00"),
        status=MonitoredStatus.active,
    )
    db_session.add(outro_monitorado)
    db_session.commit()

    response = client.get("/monitored/")
    assert response.status_code == 200

    payload = response.json()
    counts = {item["id"]: item["competitors_count"] for item in payload}

    assert counts[str(monitored.id)] == 2
    assert counts[str(outro_monitorado.id)] == 0
    
def test_create_scrape_product_cria_registro_pendente(monkeypatch, client, db_session, test_user, prepare_test_database):
    """Certifica que o POST cria registro pendente e agenda task"""

    captured = {}

    def fake_delay(**kwargs):
        captured.update(kwargs)

    monkeypatch.setattr(scraper_tasks.collect_product_task, "delay", fake_delay)

    response = client.post(
        "/monitored/scrape",
        json={
            "name_identification": "Console PS5",
            "product_url": "https://produto.mercadolivre.com.br/MLB-0001",
        },
    )

    assert response.status_code == 202
    assert "Scraping agendado" in response.json()["message"]

    created = (
        db_session.query(MonitoredProduct)
        .filter(
            MonitoredProduct.user_id == test_user.id,
            MonitoredProduct.product_url == "https://produto.mercadolivre.com.br/MLB-0001",
        )
        .one()
    )

    assert created.status == MonitoredStatus.pending
    assert created.last_checked is None
    assert created.product_url == "https://produto.mercadolivre.com.br/MLB-0001"
    assert captured["monitored_id"] == str(created.id)
    assert captured["name_identification"] == "Console PS5"

def test_create_scrape_product_sem_nome_aplica_fallback(monkeypatch, client, db_session, test_user, prepare_test_database):
    """Confere que o cadastro aceita nome ausente e gera fallback legível"""

    captured = {}

    def fake_delay(**kwargs):
        captured.update(kwargs)

    monkeypatch.setattr(scraper_tasks.collect_product_task, "delay", fake_delay)

    response = client.post(
        "/monitored/scrape",
        json={
            "name_identification": None,
            "product_url": "https://produto.mercadolivre.com.br/MLB-9999-produto-incrivel-123",
        },
    )

    assert response.status_code == 202

    created = (
        db_session.query(MonitoredProduct)
        .filter(
            MonitoredProduct.user_id == test_user.id,
            MonitoredProduct.product_url == "https://produto.mercadolivre.com.br/MLB-9999-produto-incrivel-123",
        )
        .one()
    )

    assert created.name_identification == "MLB 9999 produto incrivel 123"
    assert captured["name_identification"] == "MLB 9999 produto incrivel 123"

def test_create_scrape_product_detecta_duplicidade(monkeypatch, client, db_session, test_user, prepare_test_database):
    """Confere que duplicidade devolve mensagem informativa e reusa registro"""

    existing = MonitoredProduct(
        user_id=test_user.id,
        name_identification="Console PS5",
        monitoring_type=MonitoringType.scraping,
        product_url="https://produto.mercadolivre.com.br/MLB-0001",
        status=MonitoredStatus.active,
    )
    db_session.add(existing)
    db_session.commit()

    captured = {}

    def fake_delay(**kwargs):
        captured.update(kwargs)

    monkeypatch.setattr(scraper_tasks.collect_product_task, "delay", fake_delay)

    response = client.post(
        "/monitored/scrape",
        json={
            "name_identification": "Console Atualizado",
            "product_url": "https://produto.mercadolivre.com.br/MLB-0001",
        },
    )

    assert response.status_code == 409
    message = response.json()["message"]
    assert "já está sendo monitorado" in message.lower()

    reloaded = (
        db_session.query(MonitoredProduct)
        .filter(MonitoredProduct.id == existing.id)
        .one()
    )
    assert reloaded.name_identification == "Console Atualizado"
    assert captured == {}
    