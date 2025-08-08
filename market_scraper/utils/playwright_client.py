""" Módulo utilitário para uso centralizado do Playwright.

Este cliente encapsula a criação do navegador e expõe um método
para buscar o HTML de uma URL de forma simples. O objetivo é
facilitar o uso do Playwright em outros componentes da aplicação,
(especialmente no fluxo de scraping) sem que cada módulo precise
lidar diretamente com a inicialização do navegador.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from pkgutil import resolve_name
from typing import AsyncGenerator, Optional
from datetime import datetime
import random

import structlog
from playwright.async_api import async_playwright, Browser, TimeoutError as PlaywrightTimeoutError
from playwright_stealth import Stealth

from alert_app.metrics import SCRAPER_BROWSER_FALLBACK_TOTAL
from scraper_app.utils.user_agent_manager import IntelligentUserAgentManager
from scraper_app.core.config import settings


logger = structlog.get_logger("playwright_client")

class PlaywrightClient:
    """ Cliente simplificado para controlar o Playwright """
    def __init__(self, headless: bool = settings.PLAYWRIGHT_HEADLESS, timeout: int = settings.PLAYWRIGHT_TIMEOUT) -> None:
        self.headless = headless
        self.timeout = timeout
        self._browser: Optional[Browser] = None
        self._playwright = None
        self._ua_manager = IntelligentUserAgentManager()
        self._stealth = Stealth()

    async def _simulate_interacao(self, page, width: int, height: int) -> None:
        """ Realiza movimentos e rolagens sutis para parecer navegação humana """
        await page.mouse.move(random.randint(0, width), random.randint(0, height), steps=5)
        await page.wait_for_timeout(random.randint(100, 300))
        await page.mouse.wheel(0, random.randint(300, 800))
        await page.wait_for_timeout(random.randint(100, 300))

    async def __aenter__(self) -> "PlaywrightClient":
        playwright = await async_playwright().start()
        #Garante que qualquer nova página ou contexto criado utilize o stealth
        self._stealth.hook_playwright_context(playwright)
        browser = await playwright.chromium.launch(
            headless=self.headless,
            #Argumentos extras ajudam a mascarar o processo do navegador
            args=[
                "--no-sandbox",
                "--disable-dev-shm-usage",
                "--disable-blink-features=AutomationControlled"
            ],
        )
        self._browser = browser
        self._playwright = playwright
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        if self._browser:
            await self._browser.close()
        if getattr(self, "_playwright", None):
            await self._playwright.stop()

    async def fetch_html(self, url: str, *, session_id: str | None = None) -> str:
        """ Retorna o HTML gerado pelo navegador para ``url``

        O método aguarda o carregamento básico do DOM e então espera
        que o seletor principal (titulo ou preço) esteja visível. Caso
        o tempo de espera estoure, será registrado um erro, um screenshot
        será salvo e a exeção será relançada
        """
        if not self._browser:
            raise RuntimeError("PlaywrightClient is not started")

        SCRAPER_BROWSER_FALLBACK_TOTAL.inc()

        #Define dimensões aleatórias de viewport para evitar padrão fixo
        width = random.randint(1280, 1920)
        height = random.randint(720, 1080)

        context = await self._browser.new_context(
            user_agent=self._ua_manager.get_user_agent(session_id or "default"),
            java_script_enabled=True,
            viewport={"width": width, "height": height}
        )
        #Aplica stealth para reduzir a chance de bloqueio
        await self._stealth.apply_stealth_async(context)
        try:
            page = await context.new_page()
            await self._stealth.apply_stealth_async(page)
            #Carrega o DOM base antes de aguardar seletor principal
            await page.goto(url, wait_until="domcontentloaded", timeout=self.timeout)

            #Aguarda que título ou preço estejam visíveis na página
            await page.wait_for_selector(
                "h1.ui-pdp-title, .andes-money-amount__fraction, .price-tag-fraction",
                timeout=self.timeout,
                state="visible"
            )

            #Pequenas interações para simular navegação humana
            await self._simulate_interacao(page, width, height)

            html = await page.content()
            return html

        except PlaywrightTimeoutError as exc:
            logger.error("element_selector_timeout", url=url)
            await page.screenshot(
                path=f"timeout_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
            )
            raise exc
        finally:
            await context.close()

@asynccontextmanager
async def get_playwright_client(headless: bool = settings.PLAYWRIGHT_HEADLESS, timeout: int = settings.PLAYWRIGHT_TIMEOUT) -> AsyncGenerator[PlaywrightClient, None]:
    """ Context manager auxiliar para uso fácil do cliente """
    client = PlaywrightClient(headless=headless, timeout=timeout)
    await client.__aenter__()
    try:
        yield client
    finally:
        await client.__aexit__(None, None, None)
