""" Testes de integração envolvendo login e renderização de páginas """

import pytest
import mechanicalsoup

from market_scraper.services import (
    SynergicPipeline,
    MechanicalSoupLoginStep,
    RequestsHTMLRenderStep,
    BeautifulSoupExtractionStep,
)

@pytest.mark.asyncio
async def test_pipeline_com_login_e_renderização(monkeypatch: pytest.MonkeyPatch) -> None:
    """ Deve executar login, renderizar a página e extrair dados válidos """
    class NavegadorFalso:
        def open(self, url: str, **kwargs) -> None:
            pass

        def select_form(self, selector: str) -> None:
            pass

        def __setitem__(self, key: str, value: str) -> None:
            pass

        def submit_selected(self, **kwargs) -> None:
            pass

        def get_cookiejar(self):
            return {"sess": "xyz"}
        
    monkeypatch.setattr(mechanicalsoup, "StatefulBrowser", lambda: NavegadorFalso())

    html_renderizado = "<html><head><meta property='og:title' content='Produto Logado' /></head><body><span class='price'>R$ 99</span></body></html>"
    capturado: dict = {}

    class HTMLFalso:
        def __init__(self) -> None:
            self.html = ""

        def render(self, timeout: int, reload: bool) -> None:
            self.html = html_renderizado

    class RespostaFalsa:
        def __init__(self) -> None:
            self.html = HTMLFalso()

        def raise_for_status(self) -> None:
            return None

    class SessaoFalsa:
        def get(self, url: str, cookies=None, timeout: int | None = None):
            capturado["cookies"] = cookies
            return RespostaFalsa()
        
        def close(self) -> None:
            return None
        
    monkeypatch.setattr("market_scraper.services.pipeline_steps.HTMLSession", SessaoFalsa)

    passos = [
        MechanicalSoupLoginStep(login_url="https://exemplo.com/login", username="user", password="pass"),
        RequestsHTMLRenderStep(),
        BeautifulSoupExtractionStep(),
    ]
    pipeline = SynergicPipeline(steps=passos)
    resultado = await pipeline.run(shared_context={"url": "https://exemplo.com/produto"})

    assert resultado["status"] == "success"
    assert resultado["details"]["name"] == "Produto Logado"
    assert resultado["details"]["current_price"] == "R$ 99"
    assert capturado["cookies"] == {"sess": "xyz"}
    