from __future__ import annotations

""" Etapas específicas para o ``SynergicPipeline`` de scraping

Este módulo concentra implementações de ``PIpelineStep`` que utilizam
bibliotecas populares de scraping para extrair dados de forma progressiva.
Cada etapa tenta obter ``name`` e ``current_price`` do HTML disponível no
``shared_context``. Quando bem-sucedida, a etapa retorna um dicionário com
``status`` igual a ``success`` e os dados extraídos em ``details``. Caso
contrário, devolve ``status`` ``error`` para que o pipeline acione o fallback subsequente.
"""

from typing import Any
import asyncio
import json

from bs4 import BeautifulSoup
from parsel import Selector
from requests_html import HTMLSession
from selectorlib import Extractor
import requests
import extruct
import mechanicalsoup

from .synergic_pipeline import PipelineStep
from market_scraper.utils.data_quality_validator import DataQualityValidator
from market_scraper.utils.http_cache import ContentSignature, NOT_MODIFIED


class MechanicalSoupLoginStep(PipelineStep):
    """ Realiza login leve utilizando ``MechanicalSoup`` """
    def __init__(
            self,
            *,
            login_url: str | None = None,
            username: str | None = None,
            password: str | None = None,
            form_selector: str = "form",
            username_field: str = "username",
            password_field: str = "password",
    ) -> None:
        self.login_url = login_url
        self.username = username
        self.password = password
        self.form_selector = form_selector
        self.username_field = username_field
        self.password_field = password_field

    def should_run(self, shared_context: dict[str, Any]) -> bool:
        """ Executa apenas quando não existem cookies válidos no contexto """
        if shared_context.get("cookies"):
            return False
        url = self.login_url or shared_context.get("login_url")
        user = self.username or shared_context.get("username")
        pwd = self.password or shared_context.get("password")
        return bool(url and user and pwd)

    async def run(self, shared_context: dict[str, Any]) -> dict[str, Any]:
        url = self.login_url or shared_context.get("login_url")
        user = self.username or shared_context.get("username")
        pwd = self.password or shared_context.get("password")
        if not url or not user or not pwd:
            return {"status": "error"}
        
        def _login() -> mechanicalsoup.StatefulBrowser:
            browser = mechanicalsoup.StatefulBrowser()
            browser.open(url)
            try:
                browser.select_form(self.form_selector)
                browser[self.username_field] = user
                browser[self.password_field] = pwd
                browser.submit_selected()
            except Exception:
                #Mesmo se o formulário não estiver presente, retorna o browser
                pass
            return browser
        
        browser = await asyncio.to_thread(_login)
        shared_context["cookies"] = browser.get_cookiejar()
        return {"status": "success", "shared_context": {"cookies": shared_context["cookies"]}}
    
class ExtructExtractionStep(PipelineStep):
    """ Extrai dados estruturados com ``extruct`` """
    def __init__(self, *, validator: DataQualityValidator | None = None) -> None:
        self.validator = validator or DataQualityValidator()

    async def run(self, shared_context: dict[str, Any]) -> dict[str, Any]:
        html = shared_context.get("html")
        if html is None:
            url = shared_context.get("url")
            if not url:
                return {"status": "error"}
            
            def _get() -> str:
                resp = requests.get(url, cookies=shared_context.get("cookies"))
                resp.raise_for_status()
                return resp.text

            html = await asyncio.to_thread(_get)
            shared_context["html"] = html

        data = extruct.extract(html, syntaxes=["json-ld", "microdata", "opengraph"], uniform=True, errors="ignore")

        name = None
        price = None
        for item in data.get("json-ld", []):
            if isinstance(item, dict) and item.get("@type") in {"Product", "Offer"}:
                name = item.get("name")
                offers = item.get("offers") or {}
                if isinstance(offers, dict):
                    price = offers.get("price") or offers.get("lowPrice")
                price = price or item.get("price")
                break

        if not name and data.get("opengraph"):
            og = {d.get("property"): d.get("content") for d in data["opengraph"]}
            name = name or og.get("og:title")
            price = price or og.get("product:price:amount")

        details = {"name": name, "current_price": price}
        try:
            self.validator.validate(details)
        except ValueError:
            return {"status": "error"}
        
        return {
            "status": "success",
            "details": details,
            "extraction_method": self.__class__.__name__,
        }
    
class ParselExtractionStep(PipelineStep):
    """ Coleta usando ``Parsel`` / ``lxml`` """
    def __init__(self, *, validator: DataQualityValidator | None = None) -> None:
        self.validator = validator or DataQualityValidator()

    def should_run(self, shared_context: dict[str, Any]) -> bool:
        """ Evita execução quando não há HTML disponível """
        return bool(shared_context.get("html"))

    async def run(self, shared_context: dict[str, Any]) -> dict[str, Any]:
        html = shared_context.get("html")
        if not html:
            return {"status": "error"}
        sel = Selector(text=html)

        name = None
        price = None

        json_ld = sel.xpath('string(//script[@type="application/ld+json"][1])').get()
        if json_ld:
            try:
                data = json.loads(json_ld)
                name = data.get("name")
                offers = data.get("offers") or {}
                if isinstance(offers, dict):
                    price = offers.get("price") or offers.get("lowPrice")
                price = price or data.get("price")
            except Exception:
                pass

        if not name:
            name = sel.xpath('//meta[@property="og:title"]/@content').get()
        if not price:
            price = sel.xpath('//span[@id="price"]/text()').get()

        details = {"name": name, "current_price": price}
        try:
            self.validator.validate(details)
        except ValueError:
            return {"status": "error"}
        
        return {
            "status": "success",
            "details": details,
            "extraction_method": self.__class__.__name__,
        }
    
class BeautifulSoupExtractionStep(PipelineStep):
    """ Realiza extração simples com ``BeautifulSoup`` """
    def __init__(self, *, validator: DataQualityValidator | None = None) -> None:
        self.validator = validator or DataQualityValidator()

    def should_run(self, shared_context: dict[str, Any]) -> bool:
        """ Executa apenas quando o HTML já foi carregado no contexto """
        return bool(shared_context.get("html"))

    async def run(self, shared_context: dict[str, Any]) -> dict[str, Any]:
        html = shared_context.get("html")
        if not html:
            return {"status": "error"}
        soup = BeautifulSoup(html, "lxml")
        name_el = soup.select_one("meta[property='og:title']") or soup.select_one("title")
        price_el = soup.select_one("#price") or soup.select_one(".price")
        name = (
            name_el["content"] 
            if name_el and name_el.has_attr("content") 
            else name_el.get_text(strip=True) if name_el else None
        )
        price = price_el.get_text(strip=True) if price_el else None
        details = {"name": name, "current_price": price}
        try:
            self.validator.validate(details)
        except ValueError:
            return {"status": "error"}
        return {
            "status": "success",
            "details": details,
            "extraction_method": self.__class__.__name__,
        }
    
class RequestsHTMLRenderStep(PipelineStep):
    """ Renderiza JavaScript leve com ``requests-html`` """
    def __init__(self, *, timeout: int = 8) -> None:
        self.timeout = timeout

    def should_run(self, shared_context: dict[str, Any]) -> bool:
        """ Evita renderização quando o HTML já está presente """
        return not shared_context.get("html")

    async def run(self, shared_context: dict[str, Any]) -> dict[str, Any]:
        url = shared_context.get("url")
        if not url:
            return {"status": "error"}
        
        def _render() -> str:
            session = HTMLSession()
            resp = session.get(url, cookies=shared_context.get("cookies"))
            resp.html.render(timeout=self.timeout, reload=False)
            return resp.html.html
        
        html = await asyncio.to_thread(_render)
        shared_context["html"] = html
        signature = ContentSignature(url).check_or_update(html)
        if signature is NOT_MODIFIED:
            return {"status": "NOT_MODIFIED"}
        if isinstance(signature, str):
            shared_context["content_signature"] = signature
            return {
                "status": "success",
                "shared_context": {"html": html, "content_signature": signature},
            }
        return {"status": "success", "shared_context": {"html": html}}
    
class SelectorLibExtractionStep(PipelineStep):
    """ Aplica ``selectorlib`` para páginas customizadas """
    def __init__(self, *, template_path: str | None = None, validator: DataQualityValidator | None = None) -> None:
        self.template_path = template_path
        self.validator = validator or DataQualityValidator()

    def should_run(self, shared_context: dict[str, Any]) -> bool:
        """ Executa somente quando há HTML e template definido """
        return bool(shared_context.get("html") and (self.template_path or shared_context.get("selectorlib_template")))

    async def run(self, shared_context: dict[str, Any]) -> dict[str, Any]:
        html = shared_context.get("html")
        template = self.template_path or shared_context.get("selectorlib_template")
        if not html or not template:
            return {"status": "error"}
        extractor = Extractor.from_yaml_file(template)
        data = await asyncio.to_thread(extractor.extract, html)
        details = {
            "name": data.get("name"),
            "current_price": data.get("current_price") or data.get("price"),
        }
        try:
            self.validator.validate(details)
        except ValueError:
            return {"status": "error"}
        return {
            "status": "success",
            "details": details,
            "extraction_method": self.__class__.__name__,
        }
    
__all__ = [
    "MechanicalSoupLoginStep",
    "ExtructExtractionStep",
    "ParselExtractionStep",
    "BeautifulSoupExtractionStep",
    "RequestsHTMLRenderStep",
    "SelectorLibExtractionStep",
]
