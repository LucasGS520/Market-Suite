from __future__ import annotations

""" Parser simples para páginas HTML estáticas

O módulo oferece utilitários focados em coletar nome e preço a partir
de HTML estático utilizando apenas BeautifulSoup com o parser ``lxml``.
Todas as funções expõem a mesma interface, retornando um dicionário com 
``name```, ``current_price`` e ``url``. Não existem fallbacks, ou orquestrações
adicionais; o retorno é pensado para ser validado pelo ``DataQualityValidator``.
"""

import re
from decimal import Decimal, InvalidOperation
from typing import Optional

from bs4 import BeautifulSoup


GENERIC_HTML_SOURCE = "generic_html"

def _compose_price_from_parts(integer: Optional[str], fraction: Optional[str]) -> str:
    """ Concatena partes separadas do preço em formato decimal """
    if not integer:
        return ""
    digits = re.sub(r"\D", "", integer)
    decimals = re.sub(r"\D", "", fraction or "")
    if not digits:
        return ""
    if decimals:
        return f"{digits}.{decimals}"
    return digits

def _normalize_price(value: Optional[str]) -> Optional[Decimal]:
    """ Converte uma string de preço para ``Decimal`` quando possível """
    if not value:
        return None
    text = value.strip()
    if not text:
        return None
    text = re.sub(r"[^0-9.,]", "", text)
    if not text:
        return None
    if "," in text and "." in text:
        text = text.replace(".", "").replace(",", ".")
    elif "," in text:
        text = text.replace(",", ".")
    try:
        return Decimal(text)
    except InvalidOperation:
        return None

def _format_price(value: Optional[str], currency: Optional[str]) -> str:
    """ Formata o preço para o padrão brasileiro """
    number = _normalize_price(value)
    if number is None:
        return ""
    symbol_map = {
        "BRL": "R$",
    }
    sanitized_currency = (currency or "R$").strip()
    #Normalizamos o código quando a página informa apenas a sigla monetária
    symbol = symbol_map.get(sanitized_currency.upper(), sanitized_currency or "R$")
    whole, fraction = f"{number:,.2f}".split(".")
    whole = whole.replace(",", ".")
    return f"{symbol} {whole},{fraction}"

def _extract_text(soup: BeautifulSoup, selector: str, attribute: str | None = None) -> str:
    """ Retorna texto limpo ou atributo ``content`` do primeiro elemento encontrado """
    element = soup.select_one(selector)
    if not element:
        return ""
    if attribute:
        return (element.get(attribute) or "").strip()
    if element.name == "meta":
        return (element.get("content") or "").strip()
    return element.get_text(strip=True)

def _assemble_result(name: str, price: str, currency: str, url: str) -> dict[str, str] | None:
    """ Normaliza os campos e monta o dicionário de saída padronizado """
    formatted_price = _format_price(price, currency)
    if not name or not formatted_price:
        return None
    return {
        "name": name,
        "current_price": formatted_price,
        "url": url,
        "source": GENERIC_HTML_SOURCE,
    }

def parse_generic_html(html: str, url: str) -> dict[str, str] | None:
    """ Realiza uma extração genérica de nome e preço a partir da página 
    
    A extração utiliza exclusivamente seletores CSS via BeautifulSoup com o
    parser ``lxml``
    Exemplo:
        >>> parse_generic_html(
        ...     "<html><head><meta property='og:title' content='Produto' />"
        ...     "<meta itemprop='price' content='199.90' /></head></html>",
        ...     "https://exemplo.com/produto",
        ... )
        {'name': 'Produto', 'current_price': 'R$ 199,90', 'url': 'https://exemplo.com/produto'}
    """
    soup = BeautifulSoup(html, "lxml")
    name = ""
    for selector in [
        'meta[property="og:title"]',
        'meta[name="title"]',
        'meta[name="twitter:title"]',
        'meta[itemprop="name"]',
        "span#productTitle",
        "h1[data-testid='heading-product-title']",
        "title",
        "h1",
    ]:
        name = _extract_text(soup, selector)
        if name:
            break

    price = ""
    for selector in [
        'meta[itemprop="price"]',
        'meta[property="product:price:amount"]',
        'meta[property="og:price:amount"]',
        'meta[name="twitter:data1"]',
        'span[itemprop="price"]',
        'div[itemprop="price"]',
    ]:
        price = _extract_text(soup, selector)
        if price:
            break

    if not price:
        price = _extract_text(soup, "[data-testid='price-value']")
    if not price:
        combined = _compose_price_from_parts(
            _extract_text(soup, "[data-testid='price-integer']"),
            _extract_text(soup, "[data-testid='price-decimal']"),
        )
        price = combined or price
    if not price:
        combined = _compose_price_from_parts(
            _extract_text(soup, "span.a-price-whole"),
            _extract_text(soup, "span.a-price-fraction"),
        )
        price = combined or price
    if not price:
        price = _extract_text(soup, ".price", attribute=None)

    currency = ""
    for selector in [
        'meta[itemprop="priceCurrency"]',
        'meta[property="product:price:currency"]',
        'meta[property="og:price:currency"]',
        'span[itemprop="priceCurrency"]',
        '[data-testid="price-currency"]',
    ]:
        currency = _extract_text(soup, selector)
        if currency:
            break

    return _assemble_result(name, price, currency, url)

def parse_meli_html(html: str, url: str) -> dict[str, str] | None:
    """ Extrai informações básicas das páginas do Mercado Livre 
    
    A leitura do HTML utiliza apenas BeautifulSoup com o parser ``lxml`` e 
    busca diretamente pelos seletores conhecidos do marketplace.
    Exemplo:
        >>> parse_meli_html(
        ...     "<html><body><h1 class='ui-pdp-title'>Notebook</h1>"
        ...     "<span class='andes-money-amount__fraction'>3.499</span>"
        ...     "<span class='andes-money-amount__cents'>99</span>"
        ...     "</body></html>",
        ...     "https://www.mercadolivre.com.br/produto",
        ... )
        {'name': 'Notebook', 'current_price': 'R$ 3.499,99', 'url': 'https://www.mercadolivre.com.br/produto'}
    """
    soup = BeautifulSoup(html, "lxml")
    name = ""
    for selector in [
        "h1.ui-pdp-title",
        "h1[data-testid='product-title']",
        "h1",
        'meta[property="og:title"]',
    ]:
        name = _extract_text(soup, selector)
        if name:
            break

    price = _compose_price_from_parts(
        _extract_text(soup, "[data-testid='price-integer']")
        or _extract_text(soup, ".andes-money-amount__fraction")
        or _extract_text(soup, ".price-tag-fraction"),
        _extract_text(soup, "[data-testid='price-decimal']")
        or _extract_text(soup, ".andes-money-amount__cents")
        or _extract_text(soup, ".price-tag-decimal"),
    )
    if not price:
        price = _extract_text(soup, "[data-testid='price-value']")
    if not price:
        price = _extract_text(soup, 'span[itemprop="price"]')
    if not price:
        price = _extract_text(soup, 'meta[itemprop="price"]')
    if not price:
        price = _extract_text(soup, 'meta[property="product:price:amount"]')

    currency = (
        _extract_text(soup, 'meta[itemprop="priceCurrency"]')
        or _extract_text(soup, 'meta[property="product:price:currency"]')
        or _extract_text(soup, "[data-testid='price-currency']")
    )
    return _assemble_result(name, price, currency, url)

def parse_amazon_html(html: str, url: str) -> dict[str, str] | None:
    """ Captura nome e preço em páginas da Amazon Brasil 
    
    Nenhuma etapa adicional é executada além da análise do HTML por meio de
    BeautifulSoup com o parser ``lxml``.
    Exemplo:
        >>> parse_amazon_html(
        ...     "<html><body><span id='productTitle'>Cafeteira</span>"
        ...     "<span class='a-offscreen'>R$ 299,00</span></body></html>",
        ...     "https://www.amazon.com.br/dp/123",
        ... )
        {'name': 'Cafeteira', 'current_price': 'R$ 299,00', 'url': 'https://www.amazon.com.br/dp/123'}
    """
    soup = BeautifulSoup(html, "lxml")
    name = ""
    for selector in [
        "#productTitle",
        "#titleSection span",
        "#title span",
        'meta[property="og:title"]',
        'meta[name="twitter:title"]',
        "title",
    ]:
        name = _extract_text(soup, selector)
        if name:
            break

    price_text = _extract_text(soup, "#corePriceDisplay_desktop_feature_div span.a-offscreen")
    if not price_text:
        price_text = _extract_text(soup, "#apex_desktop span.a-offscreen")
    if not price_text:
        price_text = _extract_text(soup, "#price_inside_buybox")
    if not price_text:
        price_text = _extract_text(soup, "#newBuyBoxPrice span.a-offscreen")
    if not price_text:
        price_text = _extract_text(soup, ".a-price span.a-offscreen")
    if not price_text:
        price_text = _compose_price_from_parts(
            _extract_text(soup, "span.a-price-whole"),
            _extract_text(soup, "span.a-price-fraction"),
        )

    currency = (
        _extract_text(soup, 'meta[property="og:price:currency"]')
        or _extract_text(soup, 'meta[itemprop="priceCurrency"]')
        or _extract_text(soup, "span.a-price-symbol")
    )

    return _assemble_result(name, price_text, currency, url)

def parse_magalu_html(html: str, url: str) -> dict[str, str] | None:
    """ Extrai dados essenciais das páginas do Magazine Luiza 
    
    O parser faz uso exclusivo do BeautifulSoup configurado com ``lxml`` para
    navegar pelos elementos relevantes.
    Exemplo:
        >>> parse_magalu_html(
        ...     "<html><head><meta property='og:title' content='Geladeira' />"
        ...     "<meta itemprop='price' content='2599.0' /></head></html>",
        ...     "https://www.magazineluiza.com.br/produto",
        ... )
        {'name': 'Geladeira', 'current_price': 'R$ 2.599,00', 'url': 'https://www.magazineluiza.com.br/produto'}
    """
    soup = BeautifulSoup(html, "lxml")
    name = ""
    for selector in [
        'meta[property="og:title"]',
        "h1[data-testid='heading-product-title']",
        "h1",
        "title",
    ]:
        name = _extract_text(soup, selector)
        if name:
            break

    price = _extract_text(soup, 'meta[itemprop="price"]')
    if not price:
        price = _extract_text(soup, "[data-testid='price-value']")
    if not price:
        price = _compose_price_from_parts(
            _extract_text(soup, "[data-testid='price-integer']"),
            _extract_text(soup, "[data-testid='price-decimal']"),
        )
    if not price:
        price = _extract_text(soup, "span[class*='price']")

    currency = _extract_text(soup, 'meta[itemprop="priceCurrency"]') or _extract_text(
        soup, "[data-testid='price-currency']"
    )

    return _assemble_result(name, price, currency, url)


__all__ = (
    "parse_generic_html",
    "parse_meli_html",
    "parse_amazon_html",
    "parse_magalu_html",
)
