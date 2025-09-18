from __future__ import annotations

""" Parser simples para páginas HTML estáticas

O módulo oferece utilitários focados em coletar nome e preço a partir
de HTML estático utilizando apenas BeautifulSoup com o parser ``lxml``.
Todas as funções expõem a mesma interface, retornando um dicionário com 
``name```, ``current_price`` e ``url``.
"""

import re
from decimal import Decimal, InvalidOperation
from typing import Optional

from bs4 import BeautifulSoup

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
    symbol = (currency or "R$").strip() or "R$"
    whole, fraction = f"{number:,.2f}".split(".")
    whole = whole.replace(",", ".")
    return f"{symbol} {whole},{fraction}"

def _extract_text(soup: BeautifulSoup, selector: str, atribute: str | None = None) -> str:
    """ Retorna texto limpo ou atributo ``content`` do primeiro elemento encontrado """
    element = soup.select_one(selector)
    if not element:
        return ""
    if atribute:
        return (element.get(atribute) or "").strip()
    if element.name == "meta":
        return (element.get("content") or "").strip()
    return element.get_text(strip=True)

def _assemble_result(name: str, price: str, currency: str, url: str) -> dict[str, str]:
    """ Normaliza os campos e monta o dicionário de saída """
    return {
        "name": name or "",
        "current_price": _format_price(price, currency),
        "url": url,
    }

def parse_generic_html(html: str, url: str) -> dict[str, str]:
    """ Realiza uma extração genérica de nome e preço a partir da página """
    soup = BeautifulSoup(html, "lxml")
    name = ""
    for selector in [
        'meta[property="og:title"]',
        'meta[name="title"]',
        'meta[itemprop="name"]',
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
        'span[itemprop="price"]',
        'div[itemprop="price"]',
    ]:
        price = _extract_text(soup, selector)
        if price:
            break

    if not price:
        price = _extract_text(soup, ".price", atribute=None)

    currency = ""
    for selector in [
        'meta[itemprop="priceCurrency"]',
        'meta[property="product:price:currency"]',
        'meta[property="og:price:currency"]',
        'span[itemprop="priceCurrency"]',
    ]:
        currency = _extract_text(soup, selector)
        if currency:
            break

    return _assemble_result(name, price, currency, url)

def parse_meli_html(html: str, url: str) -> dict[str, str]:
    """ Extrai informações básicas das páginas do Mercado Livre """
    soup = BeautifulSoup(html, "lxml")
    name = ""
    for selector in [
        "h1.ui-pdp-title",
        "h1",
        'meta[property="og:title"]',
    ]:
        name = _extract_text(soup, selector)
        if name:
            break

    whole = _extract_text(soup, ".andes-money-amount__fraction") or _extract_text(
        soup, ".price-tag-fraction"
    )
    cents = _extract_text(soup, ".andes-money-amount__cents") or _extract_text(
        soup, ".price-tag-decimal"
    )
    price = ""
    if whole:
        digits = re.sub(r"\D", "", whole)
        if cents:
            cents = re.sub(r"\D", "", cents)
            price = f"{digits}.{cents}" if digits else ""
        else:
            price = digits

    else:
        price = _extract_text(soup, 'span[itemprop="price"]')

    currency = _extract_text(soup, 'meta[itemprop="priceCurrency"]') or _extract_text(
        soup, 'meta[property="product:price:currency"]'
    )
    return _assemble_result(name, price, currency, url)

def parse_amazon_html(html: str, url: str) -> dict[str, str]:
    """ Captura nome e preço em páginas da Amazon Brasil """
    soup = BeautifulSoup(html, "lxml")
    name = ""
    for selector in [
        "#productTitle",
        'meta[property="og:title"]',
        "title",
    ]:
        name = _extract_text(soup, selector)
        if name:
            break

    whole = _extract_text(soup, "#corePriceDisplay_desktop_feature_div span.a-offscreen")
    if not whole:
        whole = _extract_text(soup, ".apexPriceToPay span.a-offscreen")
    if not whole:
        whole = _extract_text(soup, "span.a-price-whole")
        fraction = _extract_text(soup, "span.a-price-fraction")
        if whole and fraction:
            whole = f"{whole},{fraction}"

    currency = _extract_text(soup, 'meta[property="og:price:currency"]')
    if not currency:
        currency = _extract_text(soup, "span.a-price-symbol")

    return _assemble_result(name, whole, currency, url)

def parse_magalu_html(html: str, url: str) -> dict[str, str]:
    """ Extrai dados essenciais das páginas do Magazine Luiza """
    soup = BeautifulSoup(html, "lxml")
    name = ""
    for selector in [
        'meta[property="og:title"]',
        "h1",
        "title",
    ]:
        name = _extract_text(soup, selector)
        if name:
            break

    price = _extract_text(soup, 'meta[itemprop="price"]')
    if not price:
        price = _extract_text(soup, "span[class*='price']")

    currency = _extract_text(soup, 'meta[itemprop="priceCurrency"]')

    return _assemble_result(name, price, currency, url)


__all__ = (
    "parse_generic_html",
    "parse_meli_html",
    "parse_amazon_html",
    "parse_magalu_html",
)
