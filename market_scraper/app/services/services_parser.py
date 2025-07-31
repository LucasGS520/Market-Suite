"""Funções utilitárias para extrair informações de páginas do Mercado Livre.

Este módulo reúne funções de apoio e o ``RobustProductParser`` que implementa
variáveis estratégicas de coleta de dados em páginas do Mercado Livre. Cada
estratégia fornece um ``score`` indicando a confiança da extração.
"""

import re
import json
from typing import Any, Dict, Tuple, Iterable

from bs4 import BeautifulSoup

from app.utils.data_quality_validator import DataQualityValidator
from app.metrics import PARSER_SUCCESS_TOTAL, PARSER_FAILURE_TOTAL


def _deep_search(data: Any, keys: Iterable[str]) -> Any:
    """ Busca recursivamente pela primeira ocorrência de qualquer chave """
    stack = [data]
    while stack:
        current = stack.pop()
        if isinstance(current, dict):
            for k, v in current.items():
                if k in keys:
                    return v
                stack.append(v)
        elif isinstance(current, list):
            stack.extend(current)
    return None

class CaptchaDetectedError(RuntimeError):
    """ Exceção lançada quando o HTML indica um captcha """
    pass

def looks_like_product_page(html: str) -> bool:
    """ Retorna ``True`` se o HTML possui elementos típicos de uma página de produto """
    soup = BeautifulSoup(html, "html.parser")

    #Indicadores de página de listagem devem retornar ``False`` imediatamente
    if soup.select_one(".ui-search-layout"):
        return False

    og_type = soup.find("meta", property="og:type")
    if og_type and og_type.get("content") != "product":
        return False

    #Elemento de título padrão (algumas páginas usam 'tittle' por engano)
    if soup.select_one("h1.ui-pdp-title") or soup.select_one("h1.ui-pdp-tittle"):
        return True

    #Meta tag de produto no OpenGraph
    if og_type and og_type.get("content") == "product":
        return True

    #JSON-LD com tipo Product
    for script in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(script.string or "{}")
        except json.JSONDecodeError:
            continue

        if isinstance(data, list):
            if any(isinstance(d, dict) and d.get("@type") == "Product" for d in data):
                return True
        elif isinstance(data, dict) and data.get("@type") == "Product":
            return True

    return False

def extract_shipping(soup: BeautifulSoup) -> str:
    """ Tenta identificar se o anúncio oferece frete grátis """
    text = soup.get_text(separator=" ", strip=True).lower()
    if "frete grátis" in text or "frete gratuito" in text:
        return "Frete Grátis"
    return "Não informado"

def format_decimal_price(raw: str) -> str:
    """Converte valores decimais ``1299.99`` em ``R$ 1.299,99``."""
    from decimal import Decimal

    value = Decimal(raw)
    #Aplica formatação brasileira (ponto para milhar, vírgula para centavos)
    formatted = f"{value:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return f"R$ {formatted}"

# ---------- EXTRAIR VENDEDOR ----------
def extrair_seller(soup: BeautifulSoup) -> str:
    """ Tenta identificar o vendedor responsável pelo anúncio em diversas abordagens """
    #Primeira tentativa: buscar em scripts JSON-LD embutidos na página
    for script in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(script.string or "{}")
            if seller := (data.get("seller") or {}).get("name"):
                return seller
        except json.JSONDecodeError:
            continue

    #Link direto exibido no template principal
    elem = soup.select_one("a.ui-pdp-seller__link-trigger")
    if elem and elem.text.strip():
        return elem.text.strip()

    #Outras variações de classes utilizadas em layouts antigos
    fb = soup.select_one("span.ui-seller-data-header__title")
    if fb and fb.text.strip():
        return fb.text.strip()

    return "Não informado"

# ---------- EXTRAIR DETALHES DO ANUNCIO ----------
class ProductParser:
    """Parser que combina múltiplas estratégias de extração

    Cada método `` _from_*`` tenta obter os mesmos campos a partir de diferentes
    fontes do HTML e retorna uma pontuação de confiança. O parser executa todas
    as estratégias e escolhe o resultado mais completo.
    """

    def __init__(self) -> None:
        """ Define os campos obrigatórios para considerar o resultado válido """
        self.required_fields = [
            "name",
            "url",
            "current_price",
            "thumbnail",
            "seller",
        ]
        self._validator = DataQualityValidator(self.required_fields)

    #--- ESTRATÉGIAS DE EXTRAÇÃO ---
    def _from_json_ld(self, soup: BeautifulSoup) -> Tuple[float, Dict[str, Any]]:
        """ Extrai informações de scripts ``JSON-LD`` encontrados na página """
        for script in soup.find_all("script", type="application/ld+json"):
            try:
                data = json.loads(script.string or "{}")
            except json.JSONDecodeError:
                continue

            if isinstance(data, list):
                for entry in data:
                    if isinstance(entry, dict) and entry.get("@type") == "Product":
                        data = entry
                        break

            if isinstance(data, dict) and data.get("@type") == "Product":
                offers = data.get("offers", {})
                price = offers.get("price")
                old = offers.get("priceBeforeDiscount")
                image = None
                if isinstance(data.get("image"), list):
                    image = data["image"][0]
                elif isinstance(data.get("image"), str):
                    image = data.get("image")
                if not image:
                    og_tag = soup.find("meta", property="og:image")
                    image = og_tag.get("content") if og_tag and og_tag.get("content") else None
                name = data.get("name") or data.get("headline")
                if not name:
                    h1 = soup.find("h1")
                    name = h1.get_text(strip=True) if h1 else "Nome não encontrado"

                result = {
                    "name": name,
                    "current_price": format_decimal_price(str(price)) if price else None,
                    "old_price": format_decimal_price(str(old)) if old else None,
                    "shipping": extract_shipping(soup),
                    "seller": (data.get("seller") or {}).get("name") or extrair_seller(soup),
                    "thumbnail": image
                }
                return 0.9, result
        return 0.0, {}

    def _from_preloaded_state(self, soup: BeautifulSoup) -> Tuple[float, Dict[str, Any]]:
        """ Extrai dados do objeto ``__PRELOADED_STATE__`` injetado via JavaScript """
        scripts: list[str] = []
        for sc in soup.find_all("script"):
            text = sc.string or sc.get_text()
            if not text or "__PRELOADED_STATE__" not in text:
                continue
            match = re.search(r"__PRELOADED_STATE__\s*=\s*(\{.*?\})\s*;", text, re.DOTALL)
            if match:
                scripts.append(match.group(1))

        for raw in scripts:
            try:
                data = json.loads(raw)
            except json.JSONDecodeError:
                continue

            name = _deep_search(data, ["title", "name"])
            if not name:
                h1 = soup.find("h1")
                name = h1.get_text(strip=True) if h1 else None
            price = _deep_search(data, ["price", "priceDisplay", "amount"])
            seller_info = _deep_search(data, ["seller", "sellerName", "nickname"])
            if isinstance(seller_info, dict):
                seller = seller_info.get("name") or seller_info.get("nickname")
            else:
                seller = seller_info
            if not seller:
                seller = extrair_seller(soup)

            thumb = _deep_search(data, ["thumbnail", "picture", "image", "url"])
            if isinstance(thumb, list):
                first = thumb[0]
                thumb = first.get("url") if isinstance(first, dict) else first
            if not thumb:
                og_tag = soup.find("meta", property="og:image")
                thumb = og_tag.get("content") if og_tag and og_tag.get("content") else None

            result = {
                "name": name or "Nome não encontrado",
                "current_price": format_decimal_price(str(price)) if price else None,
                "old_price": None,
                "shipping": extract_shipping(soup),
                "seller": seller or extrair_seller(soup),
                "thumbnail": thumb
            }
            if price or name:
                return 0.95, result
        return 0.0, {}

    def _from_p_page(self, soup: BeautifulSoup) -> Tuple[float, Dict[str, Any]]:
        """ Extrai dados de páginas no formato ``/p/`` com JSON embutido """
        scripts: list[str] = []
        tag = soup.find("script", id="__NEXT_DATA__")
        if tag and tag.string:
            scripts.append(tag.string)

        for sc in soup.find_all("script"):
            text = sc.string or sc.get_text()
            if not text:
                continue
            if "__PRELOADED_STATE__" in text:
                match = re.search(r"__PRELOADED_STATE__\s*=\s*(\{.*?\})\s*;", text, re.DOTALL)
                if match:
                    scripts.append(match.group(1))
            elif text.strip().startswith("{") and text.strip().endswith("}"):
                scripts.append(text.strip())

        for raw in scripts:
            try:
                data = json.loads(raw)
            except json.JSONDecodeError:
                continue

            name = _deep_search(data, ["title", "name"])
            if not name:
                h1 = soup.find("h1")
                name = h1.get_text(strip=True) if h1 else "Nome não encontrado"
            price = _deep_search(data, ["price", "priceDisplay", "amount"])
            old = _deep_search(data, ["original_price", "regular_price", "listPrice"])
            seller_info = _deep_search(data, ["seller", "sellerName", "nickname"])
            if isinstance(seller_info, dict):
                seller = seller_info.get("name") or seller_info.get("nickname")
            else:
                seller = seller_info
            thumb = _deep_search(data, ["thumbnail", "picture", "image", "url"])
            if isinstance(thumb, list):
                first = thumb[0]
                if isinstance(first, dict):
                    thumb = first.get("url") or first.get("secure_url")
                else:
                    thumb = first

            result = {
                "name": name,
                "current_price": format_decimal_price(str(price)) if price else None,
                "old_price": format_decimal_price(str(old)) if old else None,
                "shipping": extract_shipping(soup),
                "seller": seller or extrair_seller(soup),
                "thumbnail": thumb
            }
            if any(result.values()):
                return 0.85, result
        return 0.0, {}

    def parse(self, html: str, url: str) -> Dict[str, Any]:
        """ Executa todas as estratégias e retorna o melhor resultado. """
        lower = html.lower()
        if "captcha" in lower or "digite os caracteres" in lower:
            raise CaptchaDetectedError("CAPTCHA detectado ou bloqueio humano")

        soup = BeautifulSoup(html, "html.parser")
        strategies = [
            lambda: self._from_preloaded_state(soup),
            lambda: self._from_json_ld(soup),
            lambda: self._from_p_page(soup),
        ]

        results = []
        for strat in strategies:
            score, data = strat()
            if data:
                data["url"] = url
                results.append((score, data))

        if not results:
            raise ValueError("Nenhuma estratégia retornou dados")

        results.sort(key=lambda x: x[0], reverse=True)
        for _, data in results:
            try:
                self._validator.validate(data)
                PARSER_SUCCESS_TOTAL.inc()
                return data
            except ValueError:
                PARSER_FAILURE_TOTAL.inc()
                continue

        best = results[0][1]
        self._validator.validate(best)
        PARSER_SUCCESS_TOTAL.inc()
        return best

#--- API DE ALTO NÍVEL ---
class RobustProductParser(ProductParser):
    """ Alias de ``ProductParser`` para retrocompatibilidade """
    pass

def parse_product_details(html: str, url: str) -> Dict[str, Any]:
    """ Instancia ``RobustProductParser`` e executa o parse """
    parser = RobustProductParser()
    return parser.parse(html, url)
