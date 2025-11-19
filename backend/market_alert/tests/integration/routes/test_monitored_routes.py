""" Testes das rotas de produtos monitorados """

from decimal import Decimal

from market_alert.enums.enums_products import MonitoringType, MonitoredStatus, ProductStatus
from market_alert.enums.enums_comparisons import CompetitivenessStatus
from market_alert.models.models_products import MonitoredProduct, CompetitorProduct
from market_alert.models.models_comparisons import PriceComparison, PriceComparisonSummary
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
    assert payload["total"] == 2
    assert payload["page"] == 1
    assert payload["per_page"] == 50

    ids = {item["id"] for item in payload["items"]}
    assert str(monitored.id) in ids
    assert str(outro_monitorado.id) in ids

    assert len(payload["items"]) == 2

def test_list_monitored_products_aplica_paginacao(client, db_session, test_user, prepare_test_database):
    """Verifica que o endpoint respeita os parâmetros de página e itens por página"""
    for sufixo in range(3):
        produto = MonitoredProduct(
            user_id=test_user.id,
            name_identification=f"Produto {sufixo}",
            monitoring_type=MonitoringType.scraping,
            product_url=f"https://example.com/produto-{sufixo}",
            current_price=Decimal("100.00") + sufixo,
            status=MonitoredStatus.active,
        )
        db_session.add(produto)
    db_session.commit()

    response = client.get("/monitored/?page=2&per_page=1")
    assert response.status_code == 200

    payload = response.json()
    assert payload["total"] == 3
    assert payload["page"] == 2
    assert payload["per_page"] == 1
    assert len(payload["items"]) == 1

def test_list_monitored_products_filtra_por_query(client, db_session, test_user, prepare_test_database):
    """Garante que a busca textual considere o nome configurado"""
    alvo = MonitoredProduct(
        user_id=test_user.id,
        name_identification="Console Gamer", 
        monitoring_type=MonitoringType.scraping,
        product_url="https://example.com/console", 
        current_price=Decimal("5000.00"),
        status=MonitoredStatus.active,
    )
    outro = MonitoredProduct(
        user_id=test_user.id,
        name_identification="Notebook", 
        monitoring_type=MonitoringType.scraping,
        product_url="https://example.com/notebook", 
        current_price=Decimal("4500.00"),
        status=MonitoredStatus.active,
    )
    db_session.add_all([alvo, outro])
    db_session.commit()

    response = client.get("/monitored/?query=console")
    assert response.status_code == 200

    payload = response.json()
    assert payload["total"] == 1
    assert len(payload["items"]) == 1
    assert payload["items"][0]["id"] == str(alvo.id)

def test_list_monitored_products_filtra_por_status_competitivo(client, db_session, test_user, prepare_test_database):
    """Confere que o filtro de status usa o resumo mais recente de comparação"""
    produto_urgente = MonitoredProduct(
        user_id=test_user.id,
        name_identification="Produto Urgente",
        monitoring_type=MonitoringType.scraping,
        product_url="https://example.com/urgente",
        current_price=Decimal("100.00"),
        status=MonitoredStatus.active,
    )
    produto_estavel = MonitoredProduct(
        user_id=test_user.id,
        name_identification="Produto Estavel",
        monitoring_type=MonitoringType.scraping,
        product_url="https://example.com/estavel",
        current_price=Decimal("200.00"),
        status=MonitoredStatus.active,
    )
    db_session.add_all([produto_urgente, produto_estavel])
    db_session.flush()

    comparacao_urgente = PriceComparison(
        monitored_product_id=produto_urgente.id,
        data={},
    )
    comparacao_estavel = PriceComparison(
        monitored_product_id=produto_estavel.id,
        data={},
    )
    db_session.add_all([comparacao_urgente, comparacao_estavel])
    db_session.flush()

    resumo_urgente = PriceComparisonSummary(
        monitored_product_id=produto_urgente.id,
        comparison_id=comparacao_urgente.id,
        aggregates={"competitiveness_status": CompetitivenessStatus.URGENT.value},
    )
    resumo_estavel = PriceComparisonSummary(
        monitored_product_id=produto_estavel.id,
        comparison_id=comparacao_estavel.id,
        aggregates={"competitiveness_status": CompetitivenessStatus.COMPETITIVE.value},
    )
    db_session.add_all([resumo_urgente, resumo_estavel])
    db_session.commit()

    response = client.get("/monitored/?status=urgente")
    assert response.status_code == 200

    payload = response.json()
    assert payload["total"] == 1
    assert len(payload["items"]) == 1
    assert payload["items"][0]["id"] == str(produto_urgente.id)
    
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
    message = response.json()["detail"]
    assert "já está sendo monitorado" in message.lower()

    reloaded = (
        db_session.query(MonitoredProduct)
        .filter(MonitoredProduct.id == existing.id)
        .one()
    )
    assert reloaded.name_identification == "Console Atualizado"
    assert captured == {}
    