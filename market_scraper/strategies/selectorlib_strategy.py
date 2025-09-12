from __future__ import annotations

""" Estratégia de scraping baseada em SelectorLib

Esta estratégia utiliza templates YAML gerados pela extensão do
SelectorLib para extrair dados de páginas cujo layout é instável
ou difícil de manter com seletores tradicionais.
"""

from pathlib import Path
from typing import Any, Dict, Optional
from urllib.parse import urlparse

import httpx
import structlog
from selectorlib import Extractor

from .base import ScrapingStrategy
from market_scraper.utils.constants import STEALTH_HEADERS, GENERIC_COOKIES
from market_scraper.utils.data_quality_validator import DataQualityValidator
from market_scraper.utils.user_agent_manager import IntelligentUserAgentManager
from market_scraper.utils.throttle_manager import ThrottleManager
from market_scraper.utils.http_utils import extract_hostname

logger = structlog.get_logger(__name__)


class SelectorLibStrategy(ScrapingStrategy):
    """ Estratégia de scaping que utiliza templates SelectorLib """
    priority = 15

    _ua_manager = IntelligentUserAgentManager()

    def __init__(self, template_dir: Optional[Path] = None) -> None:
        """ Define o diretório onde os templates YAML estão armazenados """
        default_dir = Path(__file__).resolve().parent.parent / "selectorlib_templates"
        self.template_dir = template_dir or default_dir
        self._extractors: Dict[str, Extractor] = {}

    def supports_url(self, url: str) -> bool:
        """ Retorna ``True`` quando existe template para o domínio informado """
        domain = extract_hostname(url)
        return (self.template_dir / f"{domain}.yml").exists()
    
    async def _fetch_html(self, url: str, cookies: Optional[Dict[str, str]] = None) -> str:
        """ Faz requisição HTTP simples retornando o corpo da página """
        headers = {**STEALTH_HEADERS, "User-Agent": self._ua_manager.get_user_agent("selectorlib")}
        async with httpx.AsyncClient(
            headers=headers, 
            cookies=cookies or GENERIC_COOKIES, 
            timeout=10, 
            follow_redirects=True,
        ) as client:
            resp = await client.get(url)
        resp.raise_for_status()
        return resp.text
    
    def _get_extractor(self, domain: str) -> Extractor:
        """ Carrega e cacheia o template correspondente ao domínio """
        extractor = self._extractors.get(domain)
        if extractor is None:
            path = self.template_dir / f"{domain}.yml"
            extractor = Extractor.from_yaml_file(str(path))
            self._extractors[domain] = extractor
        return extractor
    
    async def get_data(self, url: str, headers: Optional[Dict[str, str]] = None, **kwargs: Any) -> dict:
        """ Executa o scraping utilizando o template definido para o domínio """
        throttle: ThrottleManager | None = kwargs.get("throttle_manager")
        if throttle:
            await throttle.wait_async(urlparse(url).netloc, url)

        if "cookies" in kwargs:
            html = await self._fetch_html(url, cookies=kwargs.get("cookies"))
        else:
            html = await self._fetch_html(url)
        domain = extract_hostname(url)
        extractor = self._get_extractor(domain)
        data = extractor.extract(html)

        details = {
            "name": data.get("name"),
            "url": url,
            "current_price": data.get("current_price") or data.get("price"),
        }
        try:
            DataQualityValidator(["name", "current_price"]).validate(details)
        except ValueError as exc:
            logger.warning("Falha na validação dos dados", url=url, erro=str(exc))
            return {"status": "error", "detail": str(exc)}
        return {"status": "success", "details": details}
    
__all__ = ["SelectorLibStrategy"]
