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

TimeoutConfig = float | tuple[float, float] | None

def _normalize_timeout(value: Any) -> TimeoutConfig:
    """ Normaliza valores de timeout recebidos por configuração ou contexto """
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value)
        except ValueError:
            return None
    if isinstance(value, (list, tuple)) and len(value) == 2:
        first = _normalize_timeout(value[0])
        second = _normalize_timeout(value[1])
        if isinstance(first, (int, float)) and isinstance(second, (int, float)):
            return float(first), float(second)
    return None

def _resolve_timeout(shared_context: dict[str, Any], fallback: TimeoutConfig, *keys: str) -> TimeoutConfig:
    """ Busca o timeout definido no contexto compartilhado respeitando prioridades """
    normalized_fallback = _normalize_timeout(fallback)
    if not keys:
        return normalized_fallback
    
    check_keys = list(dict.fromkeys([*keys, *(f"{key}_timeout" for key in keys)]))

    timeouts = shared_context.get("timeouts")
    if isinstance(timeouts, dict):
        for key in check_keys:
            candidate = _normalize_timeout(timeouts.get(key))
            if candidate is not None:
                return candidate
            
    for key in check_keys:
        candidate = _normalize_timeout(shared_context.get(key))
        if candidate is not None:
            return candidate
        
    return normalized_fallback

class MechanicalSoupLoginStep(PipelineStep):
    """ Realiza login leve utilizando ``MechanicalSoup`` com timeout configurável """
    def __init__(
        self,
        *,
        login_url: str | None = None,
        username: str | None = None,
        password: str | None = None,
        form_selector: str = "form",
        username_field: str = "username",
        password_field: str = "password",
        timeout: TimeoutConfig = 10.0,
    ) -> None:
        """ Inicializa a etapa permitindo configurar credenciais e limite de tempo """
        self.login_url = login_url
        self.username = username
        self.password = password
        self.form_selector = form_selector
        self.username_field = username_field
        self.password_field = password_field
        self.timeout = timeout

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
        
        timeout_value = _resolve_timeout(shared_context, self.timeout, "mechanical_soup_login", "mechanical_soup")

        def _login() -> mechanicalsoup.StatefulBrowser:
            browser = mechanicalsoup.StatefulBrowser()
            open_kwargs: dict[str, Any] = {}
            if timeout_value is not None:
                open_kwargs["timeout"] = timeout_value
            browser.open(url, **open_kwargs)
            try:
                browser.select_form(self.form_selector)
                browser[self.username_field] = user
                browser[self.password_field] = pwd
                submit_kwargs: dict[str, Any] = {}
                if timeout_value is not None:
                    submit_kwargs["timeout"] = timeout_value
                browser.submit_selected(**submit_kwargs)
            except Exception:
                #Mesmo se o formulário não estiver presente, retorna o browser
                pass
            return browser
        
        try:
            browser = await asyncio.to_thread(_login)
        except requests.exceptions.Timeout:
            return {
                "status": "timeout",
                "detail": "Tempo limite ao realizar login com MechanicalSoup",
            }
        shared_context["cookies"] = browser.get_cookiejar()
        return {
            "status": "success",
            "shared_context": {"cookies": shared_context["cookies"]}
        }
    
class ExtructExtractionStep(PipelineStep):
    """ Extrai dados estruturados com ``extruct`` respeitando timeout configurável """
    def __init__(self, *, timeout: TimeoutConfig = 8.0) -> None:
        """ Define tempo limite padrão para baixar o HTML antes da extração """
        self.timeout = timeout

    async def run(self, shared_context: dict[str, Any]) -> dict[str, Any]:
        html = shared_context.get("html")
        if html is None:
            url = shared_context.get("url")
            if not url:
                return {"status": "error"}
            
            timeout_value = _resolve_timeout(shared_context, self.timeout, "extruct", "extruct_extraction")
            
            def _get() -> str:
                request_kwargs: dict[str, Any] = {"cookies": shared_context.get("cookies")}
                if timeout_value is not None:
                    request_kwargs["timeout"] = timeout_value
                resp = requests.get(url, **request_kwargs)
                resp.raise_for_status()
                return resp.text

            try:
                html = await asyncio.to_thread(_get)
            except requests.exceptions.Timeout:
                return {
                    "status": "timeout",
                    "detail": "Tempo limite ao baixar HTML para extruct",
                }            
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
    """ Renderiza JavaScript leve com ``requests-html`` permitindo timeout configurável """
    def __init__(self, *, timeout: TimeoutConfig = 8.0) -> None:
        """ Define tempo limite padrão para a requisição e rederização do HTML """
        self.timeout = timeout

    def should_run(self, shared_context: dict[str, Any]) -> bool:
        """ Evita renderização quando o HTML já está presente """
        return not shared_context.get("html")

    async def run(self, shared_context: dict[str, Any]) -> dict[str, Any]:
        url = shared_context.get("url")
        if not url:
            return {"status": "error"}
        
        timeout_value = _resolve_timeout(shared_context, self.timeout, "requestshtml", "requests_html")
        
        def _render() -> str:
            session = HTMLSession()
            try:
                requests_kwargs: dict[str, Any] = {"cookies": shared_context.get("cookies")}
                if timeout_value is not None:
                    requests_kwargs["timeout"] = timeout_value
                resp = session.get(url, **requests_kwargs)
                resp.raise_for_status()
                render_timeout: float | None
                if isinstance(timeout_value, tuple):
                    render_timeout = timeout_value[1]
                else:
                    render_timeout = timeout_value
                render_kwargs: dict[str, Any] = {"reload": False}
                if render_timeout is not None:
                    render_kwargs["timeout"] = render_timeout
                resp.html.render(**render_kwargs)
                return resp.html.html
            finally:
                session.close()

        try:
            html = await asyncio.to_thread(_render)
        except requests.exceptions.Timeout:
            return {
                "status": "timeout",
                "detail": "Tempo limite ao baixar ou renderizar HTML com Requests-HTML",
            }
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
