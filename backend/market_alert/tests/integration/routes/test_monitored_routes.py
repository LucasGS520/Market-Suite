""" Testes das rotas de produtos monitorados """

from datetime import datetime, timedelta, timezone
from decimal import Decimal

from market_alert.enums.enums_alerts import AlertType, ChannelType, NotificationStatus
from market_alert.enums.enums_products import MonitoringType, MonitoredStatus, ProductStatus
from market_alert.enums.enums_comparisons import CompetitivenessStatus
from market_alert.models.models_products import MonitoredProduct, CompetitorProduct
from market_alert.models.models_comparisons import PriceComparison, PriceComparisonSummary
from market_alert.models.models_price_history import PriceHistory
from market_alert.models.models_alerts import AlertRule, NotificationLog
from market_alert.tasks import scraper_tasks
from shared.utils.url_validation import normalize_product_url_for_storage


def test_list_monitored_products_inclui_contagem_concorrentes(client, db_session, test_user, prepare_test_database):
    """ Garante que a rota retorne a quantidade de concorrentes por produto monitorado """
    monitored = MonitoredProduct(
        user_id=test_user.id,
        name_identification="Notebook Gamer",
        monitoring_type=MonitoringType.scraping,
        product_url="https://example.com/produto-1",
        normalized_url=normalize_product_url_for_storage("https://example.com/produto-1"),
        current_price=Decimal("4200.00"),
        status=MonitoredStatus.active,
        thumbnail="https://example.com/thumb-1.png",
        last_scraped_at=datetime(2024, 1, 10, 12, 0, tzinfo=timezone.utc),
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
        normalized_url=normalize_product_url_for_storage("https://example.com/produto-2"),
        current_price=Decimal("2550.00"),
        status=MonitoredStatus.active,
    )
    db_session.add(outro_monitorado)
    db_session.commit()

    response = client.get("/monitored/")
    assert response.status_code == 200

    payload = response.json()
    assert payload["meta"]["total"] == 2
    assert payload["meta"]["page"] == 1
    assert payload["meta"]["per_page"] == 50

    ids = {item["id"] for item in payload["items"]}
    assert str(monitored.id) in ids
    assert str(outro_monitorado.id) in ids

    assert len(payload["items"]) == 2

    item = next(
        product for product in payload["items"] if product["id"] == str(monitored.id)
    )
    assert item["owner_id"] == str(test_user.id)
    assert item["url"] == monitored.product_url
    assert item["thumbnail"] == monitored.thumbnail
    assert item["last_scraped_at"] == monitored.last_scraped_at.isoformat()
    assert "comparison_summary" in item
    assert item["comparison_summary"] is None

def test_list_monitored_products_aplica_paginacao(client, db_session, test_user, prepare_test_database):
    """Verifica que o endpoint respeita os parâmetros de página e itens por página"""
    for sufixo in range(3):
        produto = MonitoredProduct(
            user_id=test_user.id,
            name_identification=f"Produto {sufixo}",
            monitoring_type=MonitoringType.scraping,
            product_url=f"https://example.com/produto-{sufixo}",
            normalized_url=normalize_product_url_for_storage(
                f"https://example.com/produto-{sufixo}"
            ),
            current_price=Decimal("100.00") + sufixo,
            status=MonitoredStatus.active,
        )
        db_session.add(produto)
    db_session.commit()

    response = client.get("/monitored/?page=2&per_page=1")
    assert response.status_code == 200

    payload = response.json()
    assert payload["meta"]["total"] == 3
    assert payload["meta"]["page"] == 2
    assert payload["meta"]["per_page"] == 1
    assert len(payload["items"]) == 1

def test_list_monitored_products_filtra_por_query(client, db_session, test_user, prepare_test_database):
    """Garante que a busca textual considere o nome configurado"""
    alvo = MonitoredProduct(
        user_id=test_user.id,
        name_identification="Console Gamer", 
        monitoring_type=MonitoringType.scraping,
        product_url="https://example.com/console",
        normalized_url=normalize_product_url_for_storage("https://example.com/console"),
        current_price=Decimal("5000.00"),
        status=MonitoredStatus.active,
    )
    outro = MonitoredProduct(
        user_id=test_user.id,
        name_identification="Notebook", 
        monitoring_type=MonitoringType.scraping,
        product_url="https://example.com/notebook",
        normalized_url=normalize_product_url_for_storage("https://example.com/notebook"),
        current_price=Decimal("4500.00"),
        status=MonitoredStatus.active,
    )
    db_session.add_all([alvo, outro])
    db_session.commit()

    response = client.get("/monitored/?query=console")
    assert response.status_code == 200

    payload = response.json()
    assert payload["meta"]["total"] == 1
    assert len(payload["items"]) == 1
    assert payload["items"][0]["id"] == str(alvo.id)

def test_list_monitored_products_filtra_por_status_competitivo(client, db_session, test_user, prepare_test_database):
    """Confere que o filtro de status usa o resumo mais recente de comparação"""
    produto_urgente = MonitoredProduct(
        user_id=test_user.id,
        name_identification="Produto Urgente",
        monitoring_type=MonitoringType.scraping,
        product_url="https://example.com/urgente",
        normalized_url=normalize_product_url_for_storage("https://example.com/urgente"),
        current_price=Decimal("100.00"),
        status=MonitoredStatus.active,
    )
    produto_estavel = MonitoredProduct(
        user_id=test_user.id,
        name_identification="Produto Estavel",
        monitoring_type=MonitoringType.scraping,
        product_url="https://example.com/estavel",
        normalized_url=normalize_product_url_for_storage("https://example.com/estavel"),
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
    assert payload["meta"]["total"] == 1
    assert len(payload["items"]) == 1
    assert payload["items"][0]["id"] == str(produto_urgente.id)
    assert payload["items"][0]["competitiveness_status"] == CompetitivenessStatus.URGENT.value
    
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
    payload = response.json()
    assert "Scraping agendado" in payload["message"]

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
    assert payload["id"] == str(created.id)
    assert payload["url"] == created.normalized_url
    assert datetime.fromisoformat(payload["created_at"]) == created.created_at
    assert captured["monitored_id"] == str(created.id)
    assert captured["name_identification"] == "Console PS5"

def test_create_scrape_product_com_concorrente_inicial(monkeypatch, client, db_session, test_user, prepare_test_database):
    """Garante que o concorrente inicial é criado e enfileirado após o monitorado"""

    captured: list[tuple[str, dict]] = []
    user_id = test_user.id

    def fake_monitored_delay(**kwargs):
        captured.append(("monitored", kwargs))

    def fake_competitor_delay(**kwargs):
        captured.append(("competitor", kwargs))

    monkeypatch.setattr(scraper_tasks.collect_product_task, "delay", fake_monitored_delay)
    monkeypatch.setattr(scraper_tasks.collect_competitor_task, "delay", fake_competitor_delay)

    response = client.post(
        "/monitored/scrape",
        json={
            "name_identification": "Console PS5",
            "product_url": "https://produto.mercadolivre.com.br/MLB-0002",
            "initial_competitor": {
                "product_url": "https://loja.com/oferta-ps5",
                "name": "Loja Beta",
            },
        },
    )

    assert response.status_code == 202

    monitored = (
        db_session.query(MonitoredProduct)
        .filter(
            MonitoredProduct.user_id == user_id,
            MonitoredProduct.product_url == "https://produto.mercadolivre.com.br/MLB-0002",
        )
        .one()
    )

    competitor = (
        db_session.query(CompetitorProduct)
        .filter(CompetitorProduct.monitored_product_id == monitored.id)
        .one()
    )

    assert competitor.name_competitor == "Loja Beta"
    assert competitor.product_url == "https://loja.com/oferta-ps5"
    assert captured[0][0] == "monitored"
    assert captured[1][0] == "competitor"
    assert captured[1][1]["monitored_product_id"] == str(monitored.id)

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
    normalized_url = normalize_product_url_for_storage(
        "https://produto.mercadolivre.com.br/MLB-0001"
    )

    existing = MonitoredProduct(
        user_id=test_user.id,
        name_identification="Console PS5",
        monitoring_type=MonitoringType.scraping,
        product_url=normalized_url,
        normalized_url=normalized_url,
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

def test_get_monitored_product_expoe_metricas_derivadas(client, db_session, test_user, prepare_test_database):
    """Confere que o detalhe inclui data de criação, variação de preço e alertas."""

    monitored = MonitoredProduct(
        user_id=test_user.id,
        name_identification="Console Premium",
        monitoring_type=MonitoringType.scraping,
        product_url="https://example.com/produto/console-premium",
        normalized_url=normalize_product_url_for_storage(
            "https://example.com/produto/console-premium"
        ),
        current_price=Decimal("3999.90"),
        status=MonitoredStatus.active,
    )
    db_session.add(monitored)
    db_session.flush()

    inicio = datetime(2024, 2, 10, 12, 0, tzinfo=timezone.utc)
    history_entries = [
        PriceHistory(
            monitored_product_id=monitored.id,
            price=Decimal("4200.00"),
            currency="BRL",
            checked_at=inicio,
        ),
        PriceHistory(
            monitored_product_id=monitored.id,
            price=Decimal("4050.00"),
            currency="BRL",
            checked_at=inicio + timedelta(hours=2),
        ),
        PriceHistory(
            monitored_product_id=monitored.id,
            price=Decimal("4050.00"),
            currency="BRL",
            checked_at=inicio + timedelta(hours=3),
        ),
    ]
    expected_change_at = history_entries[1].checked_at
    db_session.add_all(history_entries)

    rule = AlertRule(
        user_id=test_user.id,
        monitored_product_id=monitored.id,
        rule_type=AlertType.PRICE_CHANGE,
        enabled=True,
    )
    db_session.add(rule)
    db_session.flush()

    notification = NotificationLog(
        user_id=test_user.id,
        alert_rule_id=rule.id,
        channel=ChannelType.EMAIL,
        subject="Preço ajustado",
        message="Valor atualizado no monitoramento",
        status=NotificationStatus.SENT,
    )
    db_session.add(notification)
    db_session.commit()

    response = client.get(f"/monitored/{monitored.id}")
    assert response.status_code == 200

    payload = response.json()
    assert payload["created_at"] == monitored.created_at.isoformat()
    monitored_since = payload.get("monitored_since", payload.get("created_at"))
    assert monitored_since == monitored.created_at.isoformat()
    payload_change = datetime.fromisoformat(payload["last_price_change_at"].replace("Z", "+00:00"))
    assert payload_change == expected_change_at
    assert payload["alerts_sent"] == 1
    