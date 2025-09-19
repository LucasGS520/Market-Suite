""" Testes unitários para etapas específicas do pipeline """

import pytest
import mechanicalsoup

from market_scraper.services import (
    MechanicalSoupLoginStep,
    RequestsHTMLRenderStep,
    SelectorLibExtractionStep,
)

@pytest.mark.asyncio
async def test_login_step_insere_cookies(monkeypatch: pytest.MonkeyPatch) -> None:
    """ Deve armazenar cookies obtidos via MechanicalSoup """
    class NavegadorFalso:
        def open(self, url: str) -> None:
            pass

        def select_form(self, selector: str) -> None:
            pass

        def __setitem__(self, key: str, value: str) -> None:
            pass

        def submit_selected(self) -> None:
            pass

        def get_cookiejar(self):
            return {"sess": "abc"}
        
    monkeypatch.setattr(mechanicalsoup, "StatefulBrowser", lambda: NavegadorFalso())
    passo = MechanicalSoupLoginStep(login_url="https://exemplo.com/login", username="user", password="pass")
    contexto = {}
    resultado = await passo.run(contexto)

    assert resultado["status"] == "success"
    assert contexto["cookies"] == {"sess": "abc"}

@pytest.mark.asyncio
async def test_requests_html_render_step(monkeypatch: pytest.MonkeyPatch) -> None:
    """ Deve renderizar HTML utilizando cookies do contexto """
    capturado: dict = {}
    
    class HTMLFalso:
        def __init__(self) -> None:
            self.html = ""

        def render(self, timeout: int, reload: bool) -> None:
            self.html = (
                "<html><head><title>Produto Dinâmico</title></head>"
                "<body><span id='price'>R$ 10</span></body></html>"
            )

    class RespostaFalsa:
        def __init__(self) -> None:
            self.html = HTMLFalso()

    class SessaoFalsa:
        def get(self, url: str, cookies=None):
            capturado["cookies"] = cookies
            return RespostaFalsa()
        
    monkeypatch.setattr("market_scraper.services.pipeline_steps.HTMLSession", SessaoFalsa)
    passo = RequestsHTMLRenderStep()
    contexto = {"url": "https://exemplo.com", "cookies": {"sess": "abc"}}
    resultado = await passo.run(contexto)

    assert resultado["status"] == "success"
    assert resultado["details"]["name"] == "Produto Dinâmico"
    assert resultado["details"]["current_price"] == "R$ 10" 
    assert "<span id='price'" in contexto["html"]
    assert capturado["cookies"] == {"sess": "abc"}

@pytest.mark.asyncio
async def test_selectorlib_extraction_step(monkeypatch: pytest.MonkeyPatch) -> None:
    """ Deve extrair dados usando template do SelectorLib """
    class ExtratorFalso:
        def extract(self, html: str) -> dict:
            return {"name": "Produto Teste", "price": "R$ 50"}
        
    monkeypatch.setattr("market_scraper.strategies.selectorlib_strategy.load_selectorlib_extractor", lambda path: ExtratorFalso())
    passo = SelectorLibExtractionStep(template_path="qualquer_caminho.yaml")
    contexto = {"html": "<html></html>"}
    resultado = await passo.run(contexto)

    assert resultado["status"] == "success"
    assert resultado["details"]["name"] == "Produto Teste"
    assert resultado["details"]["current_price"] == "R$ 50"
