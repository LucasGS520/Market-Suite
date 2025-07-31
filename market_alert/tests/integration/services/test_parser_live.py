"""Testes de integração ao parser realizando requisições reais."""

import os
import requests
import pytest
from app.services.services_parser import parse_product_details, RobustProductParser

@pytest.mark.integration
@pytest.mark.skipif(not os.getenv("RUN_LIVE_TESTS"), reason="requires internet")
def test_parser_with_live_meli_html():
    #Escolha um produto estável do mercado livre:
    url = "https://www.mercadolivre.com.br/smart-tv-58-philco-led-4k-google-tv-hdr10-p58kga/p/MLB48895726?pdp_filters=deal%3AMLB779362-1#polycard_client=homes-korribanSearchTodayPromotions&searchVariation=MLB48895726&wid=MLB4060862571&position=15&search_layout=grid&type=product&tracking_id=5b7663cb-7d83-4d04-957f-4e8967807fa6&sid=search&c_id=/home/today-promotions-recommendations/element&c_uid=ec9245e7-1660-45ac-93ec-90a6187ea004"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
    }

    #Busca o HTML real
    resp = requests.get(url, headers=headers, timeout=15)
    assert resp.status_code == 200, f"Página indisponível: {resp.status_code}"

    #Chama o parser
    data = parse_product_details(resp.text, url)

    #Imprime o resultado completo no console
    print("\n\n===== PARSER LIVE OUTPUT =====")
    for key, value in data.items():
        print(f"{key}: {value}")
    print("=====================================\n")

    #Valida campos mínimos
    assert isinstance(data, dict)
    assert data.get("name") and len(data["name"]) > 0
    assert data.get("current_price", "").startswith("R$")
    assert data.get("shipping") in ("Frete Grátis", "Não Informado")
    assert data.get("seller") and isinstance(data["seller"], str)
    assert data.get("thumbnail", "").startswith("http")
