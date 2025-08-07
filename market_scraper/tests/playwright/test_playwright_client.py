import pytest
from playwright.async_api import TimeoutError as PlaywrightTimeoutError

from scraper_app.utils.playwright_client import PlaywrightClient

class DummyPage:
    def __init__(self, raise_timeout: bool = False) -> None:
        self.goto_args = None
        self.selectors = []
        self.raise_timeout = raise_timeout
        self.screenshot_path = None
        self.screenshot_called = False

    async def goto(self, url, wait_until=None, timeout=None):
        self.goto_args = (url, wait_until, timeout)

    async def wait_for_selector(self, selector, timeout=None, state=None):
        self.selectors.append((selector, timeout, state))
        if self.raise_timeout:
            raise PlaywrightTimeoutError("timeout")

    async def screenshot(self, path=None):
        self.screenshot_called = True
        self.screenshot_path = path

    async def content(self):
        return "<html></html>"

    async def add_init_script(self, *_a, **_k):
        pass

class DummyContext:
    def __init__(self, page):
        self.page = page
    async def new_page(self):
        return self.page
    async def close(self):
        pass
    async def add_init_script(self, *_a, **_k):
        pass

class DummyBrowser:
    def __init__(self, page):
        self.page = page
    async def new_context(self, **k):
        return DummyContext(self.page)

@pytest.mark.asyncio
async def test_fetch_html_aguarda_titulo(monkeypatch):
    page = DummyPage()
    browser = DummyBrowser(page)
    client = PlaywrightClient()
    client._browser = browser
    html = await client.fetch_html("https://example.com")
    assert html == "<html></html>"
    assert page.goto_args[1] == "domcontentloaded"
    assert len(page.selectors) == 1
    selector, _, state = page.selectors[0]
    assert selector == "h1.ui-pdp-title, .andes-money-amount__fraction, .price-tag-fraction"
    assert state == "visible"

@pytest.mark.asyncio
async def test_fetch_html_timeout_raises():
    page = DummyPage(raise_timeout=True)
    browser = DummyBrowser(page)
    client = PlaywrightClient()
    client._browser = browser
    with pytest.raises(PlaywrightTimeoutError):
        await client.fetch_html("http://example.com")
    assert page.screenshot_called
