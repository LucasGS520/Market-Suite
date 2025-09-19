from __future__ import annotations

""" Etapas específicas para o ``SynergicPipeline`` de scraping

Este módulo concentra implementações de ``PipelineStep`` que utilizam
bibliotecas populares de scraping e parsing para extrair dados progressivamente.
Cada etapa tenta obter ``name`` e ``current_price`` do HTML disponível no
``shared_context``. Quando bem-sucedida, a etapa retorna um dicionário com
``status`` igual a ``success`` e os dados extraídos em ``details``. A
validação do conteúdo e o controle de fallback ficam a cargo do ``SynergicPipeline``.
"""

from typing import Any
import asyncio

from requests_html import HTMLSession
import requests
import mechanicalsoup

from .synergic_pipeline import PipelineStep
from market_scraper.utils.http_cache import ContentSignature, NOT_MODIFIED
from market_scraper.parsers import (
    parse_with_extruct,
    parse_with_parsel,
    parse_with_beautifulsoup,
    parse_with_requests_html,
    parse_with_selectorlib,
)

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
        return {
            "status": "success", 
            "shared_context": {"cookies": shared_context["cookies"]}
        }
    
class ExtructExtractionStep(PipelineStep):
    """ Extrai dados estruturados com ``extruct`` """
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

        details = parse_with_extruct(html, shared_context.get("url"))
        return {
            "status": "success",
            "details": details,
            "extraction_method": self.__class__.__name__,
        }
    
class ParselExtractionStep(PipelineStep):
    """ Coleta usando ``Parsel`` / ``lxml`` """
    def should_run(self, shared_context: dict[str, Any]) -> bool:
        """ Evita execução quando não há HTML disponível """
        return bool(shared_context.get("html"))

    async def run(self, shared_context: dict[str, Any]) -> dict[str, Any]:
        html = shared_context.get("html")
        if not html:
            return {"status": "error"}
        details = parse_with_parsel(html, shared_context.get("url"))
        return {
            "status": "success",
            "details": details,
            "extraction_method": self.__class__.__name__,
        }
    
class BeautifulSoupExtractionStep(PipelineStep):
    """ Realiza extração simples com ``BeautifulSoup`` """
    def should_run(self, shared_context: dict[str, Any]) -> bool:
        """ Executa apenas quando o HTML já foi carregado no contexto """
        return bool(shared_context.get("html"))

    async def run(self, shared_context: dict[str, Any]) -> dict[str, Any]:
        html = shared_context.get("html")
        if not html:
            return {"status": "error"}
        details = parse_with_beautifulsoup(html, shared_context.get("url"))
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
        shared_updates: dict[str, Any] = {"html": html}
        
        if signature is NOT_MODIFIED:
            return {"status": "NOT_MODIFIED", "shared_context": shared_updates}
        
        if isinstance(signature, str):
            shared_context["content_signature"] = signature
            shared_updates["content_signature"] = signature

        details = parse_with_requests_html(html, shared_context.get("url"))
        return {
            "status": "success",
            "details": details,
            "shared_context": shared_updates,
            "extraction_method": self.__class__.__name__,
        }
    
class SelectorLibExtractionStep(PipelineStep):
    """ Aplica ``selectorlib`` para páginas customizadas """
    def __init__(self, *, template_path: str | None = None) -> None:
        self.template_path = template_path

    def should_run(self, shared_context: dict[str, Any]) -> bool:
        """ Executa somente quando há HTML e template definido """
        return bool(shared_context.get("html") and (self.template_path or shared_context.get("selectorlib_template")))

    async def run(self, shared_context: dict[str, Any]) -> dict[str, Any]:
        html = shared_context.get("html")
        template = self.template_path or shared_context.get("selectorlib_template")
        if not html or not template:
            return {"status": "error"}
        
        try:
            details = await asyncio.to_thread(
                parse_with_selectorlib,
                html,
                shared_context.get("url"),
                template_path=template,
            )
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
