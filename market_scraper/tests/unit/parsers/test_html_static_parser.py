""" Testes unitários para o parser simplificado de HTML estático """

from __future__ import annotations

import pytest

from market_scraper.parsers.html_static import (
    parse_generic_html,
    parse_meli_html,
    parse_amazon_html,
    parse_magalu_html,
)


def test_parse_generic_html_meta_tags() -> None:
    """ Valida extração de meta tags para nome, preço e moeda  """
    html = (
        "<html><head>"
        '<meta property="og:title" content="Produto Meta" />'
        '<meta property="product:price:amount" content="349.99" />'
        '<meta property="product:price:currency" content="USD" />'
        "</head></html>"
    )
    url = "https://exemplo.com/meta"

    resultado = parse_generic_html(html, url)

    assert resultado == {
        "name": "Produto Meta",
        "current_price": "USD 349,99",
        "url": url,
    }

def test_parse_generic_html_fallback_para_titulo_e_classe_price() -> None:
    """ Garante uso de título da página e classe ``price`` quando meta tags ausentes """
    html = (
        "<html><head><title>Produto Sem Meta</title></head><body>"
        '<span class="price">R$ 129,90</span>'
        "</body></html>"
    )
    url = "https://exemplo.com/fallback"

    resultado = parse_generic_html(html, url)

    assert resultado == {
        "name": "Produto Sem Meta",
        "current_price": "R$ 129,90",
        "url": url,
    }

def test_parse_generic_html_retorna_campos_vazios() -> None:
    """ Ausência de título e preço deve resultar em campos vazios """
    url = "https://exemplo.com/incompleto"
    
    resultado = parse_generic_html("<html><body></body></html>", url)
    
    assert resultado == {
        "name": "", 
        "current_price": "", 
        "url": url,
    }

def test_parse_meli_html_compoe_fracao_e_centavos() -> None:
    """Confere extração correta dos elementos específicos do Mercado Livre"""
    html = (
        "<html><head>"
        '<meta itemprop="priceCurrency" content="R$" />'
        "</head><body>"
        '<h1 class="ui-pdp-title">Notebook Gamer</h1>'
        '<span class="andes-money-amount__fraction">1.299</span>'
        '<span class="andes-money-amount__cents">99</span>'
        "</body></html>"
    )
    url = "https://mercadolivre.com/produto"
    
    resultado = parse_meli_html(html, url)
    
    assert resultado == {
        "name": "Notebook Gamer",
        "current_price": "R$ 1.299,99",
        "url": url,
    }

def test_parse_meli_html_fallback_itemprop_price() -> None:
    """Valida fallback para ``itemprop=price`` quando frações não existam """
    html = (
        "<html><head>"
        '<meta itemprop="priceCurrency" content="USD" />'
        "</head><body>"
        "<h1>Console Importado</h1>"
        '<span itemprop="price">USD 499,90</span>'
        "</body></html>"
    )
    url = "https://mercadolivre.com/produto/importado"
    
    resultado = parse_meli_html(html, url)
    
    assert resultado == {
        "name": "Console Importado",
        "current_price": "USD 499,90",
        "url": url,
    }

def test_parse_meli_html_sem_dados_retorna_vazio() -> None:
    """Ausência de título e preço deve resultar em campos vazios"""
    url = "https://mercadolivre.com/produto/vazio"
    
    resultado = parse_meli_html("<html><body></body></html>", url)
    
    assert resultado == {
        "name": "",
        "current_price": "",
        "url": url,
    }

def test_parse_amazon_html_usa_a_offscreen() -> None:
    """Garante extração de preço exibido no elemento ``a-offscreen`` principal """
    html = (
        "<html><head>"
        '<meta property="og:price:currency" content="R$" />'
        "</head><body>"
        '<span id="productTitle">Kindle Paperwhite</span>'
        '<div id="corePriceDisplay_desktop_feature_div"><span class="a-offscreen">R$ 399,00</span></div>'
        "</body></html>"
    )
    url = "https://amazon.com.br/dp/kindle"
    
    resultado = parse_amazon_html(html, url)
    
    assert resultado == {
        "name": "Kindle Paperwhite",
        "current_price": "R$ 399,00",
        "url": url,
    }

def test_parse_amazon_html_monta_parte_inteira_e_decimal() -> None:
    """Verifica combinação de partes inteiras e decimais quando necessário"""
    html = (
        "<html><body>"
        '<span id="productTitle">Echo Dot</span>'
        '<span class="a-price-whole">279</span>'
        '<span class="a-price-fraction">90</span>'
        '<span class="a-price-symbol">R$</span>'
        "</body></html>"
    )
    url = "https://amazon.com.br/dp/echo"
    
    resultado = parse_amazon_html(html, url)
    
    assert resultado == {
        "name": "Echo Dot",
        "current_price": "R$ 279,90",
        "url": url,
    }

def test_parse_amazon_html_sem_preco_retorna_vazio() -> None:
    """Quando o preço não está presente o campo deve ficar vazio"""
    html = "<html><body><span id=\"productTitle\">Produto Sem Preço</span></body></html>"
    url = "https://amazon.com.br/dp/sem-preco"
    
    resultado = parse_amazon_html(html, url)
    
    assert resultado == {
        "name": "Produto Sem Preço", 
        "current_price": "", 
        "url": url,
    }

def test_parse_magalu_html_usa_meta_itemprop_price() -> None:
    """Confirma extração de nome e preço através de meta tags do Magazine Luiza """
    html = (
        "<html><head>"
        '<meta property="og:title" content="Smart TV" />'
        '<meta itemprop="price" content="2599.90" />'
        '<meta itemprop="priceCurrency" content="R$" />'
        "</head><body></body></html>"
    )
    url = "https://magalu.com/produto"
    
    resultado = parse_magalu_html(html, url)
    
    assert resultado == {
        "name": "Smart TV", 
        "current_price": "R$ 2.599,90", 
        "url": url
    }

def test_parse_magalu_html_fallback_para_classe_price() -> None:
    """Garante leitura do campo ``priceValue`` no estado inicial"""
    html = (
        "<html><head><title>Ventilador</title></head><body>"
        '<span class="product-price__value">R$ 189,99</span>'
        "</body></html>"
    )
    url = "https://magalu.com/produto/ventilador"
    
    resultado = parse_magalu_html(html, url)
    
    assert resultado == {
        "name": "Ventilador", 
        "current_price": "R$ 189,99", 
        "url": url
    }

def test_parse_magalu_html_sem_informacoes_retorna_vazio() -> None:
    """Quando nenhum dado é encontrado os campos devem permanecer vazios"""
    url = "https://magalu.com/produto/vazio"
    
    resultado = parse_magalu_html("<html><body></body></html>", url)
    
    assert resultado == {
        "name": "", 
        "current_price": "", 
        "url": url,
    }
