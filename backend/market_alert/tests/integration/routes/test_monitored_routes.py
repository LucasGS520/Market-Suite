""" Testes das rotas de produtos monitorados """

from decimal import Decimal

from market_alert.enums.enums_products import MonitoringType, MonitoredStatus, ProductStatus
from market_alert.models.models_products import MonitoredProduct, CompetitorProduct


def test_list_monitored_products_inclui_contagem_concorrentes(client, db_session, test_user, prepare_test_database):
    """ Garante que a rota retorne a quantidade de concorrentes por produto monitorado """
    monitored = MonitoredProduct(
        user_id=test_user.id,
        name_identification="Notebook Gamer",
        monitoring_type=MonitoringType.scraping,
        product_url="https://example.com/produto-1",
        target_price=Decimal("4000.00"),
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
        target_price=Decimal("2500.00"),
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
    