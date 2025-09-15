from __future__ import annotations

from .json_endpoint import cache_manager

""" Estratégias para HTML estático

Utilizam inicialmente extruct para extrair dados estruturados (JSON-LD, 
Microdata e Open Graph) em seguida prioriza Parsel/lxml para extrair 
nome e preço via JSON-LD e meta-tags; BeautifulSoup(lxml) é utilizado apenas como fallback. 
"""

import json
import re
from decimal import Decimal
from typing import Any, Dict, Optional
from urllib.parse import urlparse

import asyncio
import httpx
import structlog
from bs4 import BeautifulSoup
from parsel import Selector
import logging
from time import perf_counter

from shared.metrics.metrics_parser import PARSER_FAILURE_TOTAL, PARSER_SUCCESS_TOTAL, PARSER_DURATION_SECONDS

from .base import ScrapingStrategy
from market_scraper.utils.constants import STEALTH_HEADERS, GENERIC_COOKIES
from market_scraper.utils.data_quality_validator import DataQualityValidator
from market_scraper.utils.user_agent_manager import IntelligentUserAgentManager
from market_scraper.utils.intelligent_cache import IntelligentCacheManager
from market_scraper.utils.http_utils import extract_hostname
from market_scraper.utils.http_cache import get_cache_headers, store_cache_headers, ContentSignature, NOT_MODIFIED
from market_scraper.utils.robots_txt import RobotsTxtParser
from market_scraper.utils.throttle_manager import ThrottleManager
from market_scraper.utils.extract_structured_data import extract_structured_data


#Logger estruturado para acompanhar eventos de scraping
logger = structlog.get_logger(__name__)

#Logger padrão para capturar mensagens em ambientes de teste
py_logger = logging.getLogger(__name__)

#Instância compartilhada do cache inteligente para leitura de headers e conteúdos
cache_manager = IntelligentCacheManager()


class HtmlStaticStrategy(ScrapingStrategy):
    """ Estratégia base para páginas HTML estáticas

    Faz GET com cabeçalhos realistas, extrai nome/preço via JSON-LD
    (``@type=Product``) e faz fallback em meta-tags. Valida com
    ``DataQualityValidator``. """

    priority = 10
    domain: str = ""

    #Gerenciador de User-Agent para rotacionar cabeçalhos e minimizar bloqueios
    _ua_manager = IntelligentUserAgentManager()

    def supports_url(self, url: str) -> bool:
        """ Verifica se a URL pertence ao domínio esperado """
        netloc = urlparse(url).netloc
        return netloc.endswith(self.domain)

    async def _fetch_html(self, url: str, cookies: Optional[Dict[str, str]] = None) -> httpx.Response:
        """ Faz GET com headers realistas e cache condicional

        Aplica User-Agent/Referer e cookies; envia ``If-None-Match`` e
        ``If-Modified-Since`` quando disponíveis, salvando ETag/Last-Modified
        no retorno. Retorna: ``httpx.Response``. Levanta ``httpx.HTTPError``
        via ``raise_for_status``. """
        parsed = urlparse(url)
        base_domain = f"{parsed.scheme}://{parsed.netloc}/"
        headers = {**STEALTH_HEADERS, "Referer": base_domain}
        #Utiliza o User-Agent previamente selecionado ou gera um novo
        headers["User-Agent"] = getattr(
            self,
            "_pending_ua",
            self._ua_manager.get_user_agent("html_static"),
        )

        marketplace = extract_hostname(url)
        cached = cache_manager.get(marketplace=marketplace, url=url)
        if cached and cached.get("data"):
            #Conteúdo já disponível no cache inteligente; evita nova requisição
            return httpx.Response(304)

        #Recupera valores de ETag/Last-Modified do cache combinado
        cache_headers = cached.get("headers") if cached else get_cache_headers(url)
        if cache_headers.get("etag"):
            headers["If-None-Match"] = cache_headers["etag"]
        if cache_headers.get("last_modified"):
            headers["If-Modified-Since"] = cache_headers["last_modified"]

        async with httpx.AsyncClient(
            headers=headers,
            cookies=cookies or GENERIC_COOKIES,
            timeout=10,
            follow_redirects=True,
        ) as client:
            resp = await client.get(url)

        #Limpa o User-Agent armazenado para a próxima chamada
        if hasattr(self, "_pending_ua"):
            delattr(self, "_pending_ua")

        #Armazena cabeçalhos de cache para futuras requisições
        store_cache_headers(
            url,
            etag=resp.headers.get("ETag"),
            last_modified=resp.headers.get("Last-Modified"),
        )

        resp.raise_for_status()
        return resp

    def _format_price(self, value: Any, currency: Optional[str]) -> str:
        """ Formata um valor numérico para o padrão monetário brasileiro """
        if value is None:
            return ""
        try:
            amount = Decimal(str(value))
        except Exception:
            return ""
        symbol = "R$" if not currency or (currency or "").upper() in {"BRL", "R$"} else (currency or "")
        formatted = f"{amount:,.2f}".replace(",", "_").replace(".", ",").replace("_", ".")
        return f"{symbol} {formatted}".strip()

    def _extract_from_structured_data(self, data: Dict[str, Any], url: str) -> dict:
        """ Tenta obter ``name`` e ``current_price`` a partir de dados estruturados 
        
        A função percorre os blocos extraídos pelo ``extruct``, caso encontre um 
        produto válido, retorna as informações formatas, se não devolve um dicionário
        vazio para permitir fallbacks posteriores
        """
        #JSON-LD
        for item in data.get("json-ld", []):
            if isinstance(item, dict) and item.get("@type") == "Product":
                offers = item.get("offers") or {}
                if isinstance(offers, list):
                    offers = offers[0] if offers else {}
                #Alguns sites usam ``AggregateOffer`` e aninham outra lista em ``offers``
                elif isinstance(offers, dict) and isinstance(offers.get("offers"), list):
                    offers = offers["offers"][0] if offers["offers"] else {}
                price = (
                    offers.get("price")
                    or offers.get("priceSpecification", {}).get("price")
                    or offers.get("lowPrice")
                    or offers.get("highPrice")
                )
                currency = offers.get("priceCurrency") or offers.get("priceSpecification", {}).get("priceCurrency")
                name = item.get("name") or item.get("description") or item.get("sku")
                return {"name": name, "url": url, "current_price": self._format_price(price, currency)}
            
        #Microdata
        for item in data.get("microdata", []):
            types = item.get("type", [])
            if any("Product" in t for t in types):
                props = item.get("properties", {})
                name = props.get("name") or props.get("description") or props.get("sku")
                offers = props.get("offers") or {}
                if isinstance(offers, list):
                    offers = offers[0] if offers else {}
                price = (
                    offers.get("price")
                    or offers.get("priceSpecification", {}).get("price")
                    or offers.get("lowPrice")
                    or offers.get("highPrice")
                )
                currency = offers.get("priceCurrency") or offers.get("priceSpecification", {}).get("priceCurrency")
                return {"name": name, "url": url, "current_price": self._format_price(price, currency)}
            
        #Open Graph
        og = data.get("opengraph") or {}
        if isinstance(og, list):
            og = og[0] if og else {}
        if og.get("og:type") == "product":
            name = og.get("og:title")
            price = og.get("product:price:amount") or og.get("og:price:amount")
            currency = og.get("product:price:currency") or og.get("og:price:currency")
            return {"name": name, "url": url, "current_price": self._format_price(price, currency)}
        
        return {}

    def _extract_from_json_ld_parsel(self, sel: Selector, url: str) -> dict:
        """ Extrai JSON-LD (prioritário) com suporte a ``@graph``/listas """
        home = perf_counter()
        try:
            scripts = sel.xpath('//script[@type="application/ld+josn"]/text()').getall()
            for raw in scripts:
                try:
                    content = json.loads(raw or "{}")
                except json.JSONDecodeError as exc:
                    logger.debug("JSON inválido em script JSON-LD", url=url, erro=str(exc))
                    continue
                items: list[Any]
                if isinstance(content, dict):
                    items = content.get("@graph", []) if "@graph" in content else [content]
                elif isinstance(content, list):
                    items = content
                else:
                    items = []
                for item in items:
                    if isinstance(item, dict) and item.get("@type") == "Product":
                        name = item.get("name") or item.get("description") or item.get("sku")
                        offers = item.get("offers") or {}
                        if isinstance(offers, list):
                            offers = offers[0] if offers else {}
                        elif isinstance(offers, dict) and isinstance(offers.get("offers"), list):
                            offers = offers["offers"][0] if offers["offers"] else {}

                        price = (
                            offers.get("price")
                            or offers.get("priceSpecification", {}).get("price")
                            or offers.get("lowPrice")
                            or offers.get("highPrice")
                        )
                        currency = offers.get("priceCurrency") or offers.get("priceSpecification", {}).get("priceCurrency")
                        PARSER_SUCCESS_TOTAL.labels(library="parsel").inc()
                        return {
                            "name": name,
                            "url": url,
                            "current_price": self._format_price(price, currency),
                        }
            PARSER_FAILURE_TOTAL.labels(library="parsel").inc()
            return {}
        except Exception as exc:
            PARSER_FAILURE_TOTAL.labels(library="parsel").inc()
            logger.exception("Erro ao extrair JSON-LD com Parsel", url=url, erro=str(exc))
            return {}
        finally:
            PARSER_DURATION_SECONDS.labels(library="parsel").observe(
                perf_counter() - home
            )

    def _extract_from_meta_tags_parsel(self, sel: Selector, url: str) -> dict:
        """ Extrai ``name`` e ``current_price`` de meta-tags (Parsel) """
        home = perf_counter()
        try:
            name_value = (
                sel.css('meta[property="og:title"]::attr(content)').get()
                or sel.css("title::text").get()
            )
            price_value = (
                sel.css('meta[itemprop="price"]::attr(content)').get()
                or sel.css('meta[property="og:price:amount"]::attr(content)').get()
                or sel.css('meta[property="product:price:amount"]::attr(content)').get()
            )
            currency_value = (
                sel.css('meta[itemprop="priceCurrency"]::attr(content)').get()
                or sel.css('meta[property="og:price:currency"]::attr(content)').get()
                or sel.css('meta[property="product:price:currency"]::attr(content)').get()
            )
            data = {
                "name": name_value,
                "url": url,
                "current_price": self._format_price(price_value, currency_value),
            }
            if data.get("name") and data.get("current_price"):
                PARSER_SUCCESS_TOTAL.labels(library="parsel").inc()
            else:
                PARSER_FAILURE_TOTAL.labels(library="parsel").inc()
            return data
        except Exception as exc:
            PARSER_FAILURE_TOTAL.labels(library="parsel").inc()
            logger.exception("Erro ao extrair meta-tags com Parsel", url=url, erro=str(exc))
            return {}
        finally:
            PARSER_DURATION_SECONDS.labels(library="parsel").observe(
                perf_counter() - home
            )
        

    def _extract_from_json_ld(self, soup: BeautifulSoup, url: str) -> dict:
        """ Procura JSON-LD (Product) com BeautifulSoup """
        home = perf_counter()
        try:
            for tag in soup.find_all("script", type="application/ld+json"):
                try:
                    content = json.loads(tag.string or "{}")
                except json.JSONDecodeError as exc:
                    logger.debug("JSON inválido em script JSON-LD (bs4)", url=url, erro=str(exc))
                    continue
            items: list[Any]
            if isinstance(content, dict):
                items = content.get("@graph", []) if "@graph" in content else [content]
            elif isinstance(content, list):
                items = content
            else:
                items = []
            for item in items:
                if isinstance(item, dict) and item.get("@type") == "Product":
                    name = item.get("name") or item.get("description") or item.get("sku")
                    offers = item.get("offers") or {}
                    #Caso ``offers`` seja uma lista, utiliza o primeiro elemento
                    if isinstance(offers, list):
                        offers = offers[0] if offers else {}
                    #Alguns sites definem ``offers`` dentro do outro bloco ``offers`` conforme o padrão ``AggregateOffer``.
                    elif isinstance(offers, dict) and isinstance(offers.get("offers"), list):
                        offers = offers["offers"][0] if offers["offers"] else {}

                    #Busca o preço em diferentes campos, incluindo ``lowPrice`` e ``highPrice`` quando ``price`` não estiver disponível.
                    price = (
                        offers.get("price")
                        or offers.get("priceSpecification", {}).get("price")
                        or offers.get("lowPrice")
                        or offers.get("highPrice")
                    )
                    #Busca a moeda diretamente ou dentro de ``priceSpecification``
                    currency = offers.get("priceCurrency") or offers.get("priceSpecification", {}).get("priceCurrency")
                    PARSER_SUCCESS_TOTAL.labels(library="beautifulsoup").inc()
                    return {
                        "name": name,
                        "url": url,
                        "current_price": self._format_price(price, currency),
                    }
            PARSER_FAILURE_TOTAL.labels(library="beautifulsoup").inc()
            return {}
        except Exception as exc:
            PARSER_FAILURE_TOTAL.labels(library="beautifulsoup").inc()
            logger.exception("Erro ao extrair JSON-LD com BeautifulSoup", url=url, erro=str(exc))
            return {}
        finally:
            PARSER_DURATION_SECONDS.labels(library="beautifulsoup").observe(
                perf_counter() - home
            )

    def _extract_from_meta_tags(self, soup: BeautifulSoup, url: str) -> dict:
        """ Extrai dados de meta-tags (alternativa ao JSON-LD) usando BeautifulSoup """
        home = perf_counter()
        try:
            name = soup.find("meta", property="og:title") or soup.find("title")
            price = (
                soup.find("meta", itemprop="price")
                or soup.find("meta", property="og:price:amount")
                or soup.find("meta", property="product:price:amount")
            )
            currency = (
                soup.find("meta", itemprop="priceCurrency")
                or soup.find("meta", property="og:price:currency")
                or soup.find("meta", property="product:price:currency")
            )

            #Determina o valor do nome considerando meta-tags e a tag <title>
            name_value: Optional[str] = None
            if name:
                if name.name == "meta":
                    #Em meta-tags o nome é definido pelo atributo ``content``
                    name_value = name.get("content")
                else:
                    #Para a tag <title> utilizamos o texto interno
                    name_value = name.text

            data = {
                "name": name_value,
                "url": url,
                "current_price": self._format_price(
                    price.get("content") if price else None,
                    currency.get("content") if currency else None,
                ),
            }
            if data.get("name") and data.get("current_price"):
                PARSER_SUCCESS_TOTAL.labels(library="beautifulsoup").inc()
            else:
                PARSER_FAILURE_TOTAL.labels(library="beautifulsoup").inc()
            return data
        except Exception as exc:
            PARSER_FAILURE_TOTAL.labels(library="beautifulsoup").inc()
            logger.exception(
                "Erro ao extrair meta-tags com BeautifulSoup", url=url, erro=str(exc)
            )
            return {}
        finally:
            PARSER_DURATION_SECONDS.labels(library="beautifulsoup").observe(
                perf_counter() - home
            )

    def _parse_html(self, html: str, url: str) -> dict:
        """ Orquestra a extração inicia tentando extrair dados estruturados com extruct priorizando Parsel/lxml com fallback para BeautifulSoup(lxml) """
        structured = extract_structured_data(html, url)
        data = self._extract_from_structured_data(structured, url)
        if data.get("name") and data.get("current_price"):
            return data

        sel = Selector(text=html)
        data = self._extract_from_json_ld_parsel(sel, url)
        if not data.get("name") or not data.get("current_price"):
            data = self._extract_from_meta_tags_parsel(sel, url)
        if data.get("name") or not data.get("current_price"):
            return data
        
        soup = BeautifulSoup(html, "lxml")
        data = self._extract_from_json_ld(soup, url)
        if not data.get("name") or not data.get("current_price"):
            data = self._extract_from_meta_tags(soup, url)
        return data

    async def get_data(self, url: str, headers: Optional[Dict[str, str]] = None, **kwargs: Any) -> dict:
        """ Executa scraping com robots.txt, throttle, cache e validação

        Fluxo: respeita robots.txt (allow/delay), aplica throttle, baixa HTML,
        verifica assinatura/ETag, extrai e valida ``name``/``current_price``.
        Retorna: ``{"status": success|error|blocked|NOT_MODIFIED, ...}``.
        Em 403, registra bloqueio no ``recovery_manager`` quando informado. """
        #Define o User-Agent que será utilizado tanto para o robots.txt quanto para a requisição
        ua = self._ua_manager.get_user_agent("html_static")
        parser = RobotsTxtParser(base_url=url)
        path = urlparse(url).path or "/"

        #Interrompe caso o caminho seja proibido pelo robots.txt
        if not await parser.is_allowed(path, ua):
            return {"status": "blocked", "detail": "Bloqueado pelo robots.txt"}
        #Aguarda o tempo recomendado antes de continuar
        delay = await parser.get_crawl_delay(ua)
        if delay:
            await asyncio.sleep(delay)
        #Armazena o User-Agent para uso na requisição HTTP
        self._pending_ua = ua

        #Aguarda o sinal do ``ThrottleManager`` quando disponível
        throttle: ThrottleManager | None = kwargs.get("throttle_manager")
        if throttle:
            await throttle.wait_async(urlparse(url).netloc, url)

        try:
            #Realiza o download da página alvo
            if "cookies" in kwargs:
                resp = await self._fetch_html(url, cookies=kwargs.get("cookies"))
            else:
                resp = await self._fetch_html(url)
            #Suporte a testes que retornam apenas string em ``_fetch_html``
            if not isinstance(resp, httpx.Response):
                resp = httpx.Response(200, text=str(resp))
        except httpx.HTTPError as exc:
            #Registra detalhes da resposta para facilitar depuração
            resp = getattr(exc, "response", None)
            location = resp.headers.get("location") if resp else None
            body = resp.text[:200] if resp and resp.text else None
            #Registra também no logger padrão para que testes possam capturar a mensagem
            py_logger.exception(
                "Falha na requisição HTML url=%s status=%s location=%s body=%s",
                url,
                getattr(resp, "status_code", None),
                location,
                body,
            )
            logger.exception(
                "Falha na requisição HTML",
                url=url,
                status=getattr(resp, "status_code", None),
                location=location,
                body=body,
            )

            #Caso o domínio responda com 403, registra o bloqueio
            if resp and resp.status_code == 403:
                recovery_manager = kwargs.get("recovery_manager")
                if recovery_manager:
                    #Informa ao gerenciador que houve bloqueio pelo domínio
                    recovery_manager.register_block(url=url, status=403)
                domain = urlparse(url).netloc
                return {
                    "status": "blocked",
                    "detail": f"HTTP 403 recebido de {domain}",
                }
            #Se ocorrer erro de rede ou status inválido, sinaliza falha genérica
            return {"status": "error"}

        if resp.status_code == 304:
            #Quando o servidor indica que o conteúdo não mudou, repassa o status
            return {"status": "NOT_MODIFIED"}

        html = resp.text

        #Verifica a assinatura do conteúdo para detectar mudanças de forma independente
        signature = ContentSignature(url).check_or_update(html)
        if signature is NOT_MODIFIED:
            return {"status": "NOT_MODIFIED"}

        data = self._parse_html(html, url)
        try:
            #Valida apenas os campos essenciais antes de retornar
            DataQualityValidator(["name", "current_price"]).validate(data)
        except ValueError as exc:
            #Registra a falha de validação com o detalhe da exceção para que possamos rastrear rapidamente o motivo do erro
            logger.warning("Falha na validação dos dados", url=url, erro=str(exc))
            #Propaga o motivo da falha de volta para o endpoint chamador e permitindo que a API informe ao cliente qual campo foi rejeitado
            return {"status": "error", "detail": str(exc)}
        return {"status": "success", "details": data}


# ---------- ESTRATÉGIA DO HTML ESTÁTICO DOS MARKETPLACES ---------- #
class MercadoLivreHtmlStaticStrategy(HtmlStaticStrategy):
    """ Estratégia para páginas estáticas do Mercado Livre """
    domain = "mercadolivre.com.br"

    def _parse_html(self, html: str, url: str) -> dict:
        """ Extrai nome/preço via JSON-LD/meta e fallbacks específicos do Mercado Livre """
        structured = extract_structured_data(html, url)
        data = self._extract_from_structured_data(structured, url)
        if data.get("name") and data.get("current_price"):
            return data
        
        #Prioriza Parsel/lxml
        sel = Selector(text=html)
        data = self._extract_from_json_ld_parsel(sel, url)
        if not data.get("name") or not data.get("current_price"):
            data = self._extract_from_meta_tags_parsel(sel, url)

        #Fallback para BeautifulSoup(lxml) apenas se necessário
        soup = BeautifulSoup(html, "lxml")
        if not data.get("name") or not data.get("current_price"):
            data_bs = self._extract_from_json_ld(soup, url)
            if not data_bs.get("name") or not data_bs.get("current_price"):
                data_bs = self._extract_from_meta_tags(soup, url)
            if data_bs.get("name") and data_bs.get("current_price"):
                return data_bs

        if data.get("name") and data.get("current_price"):
            return data

        # --- FALLBACK PARA SELETORES ESPECÍFICOS DO MERCADO LIVRE (PARSEL) ---
        title = (
            sel.css("h1.ui-pdp-title::text").get()
            or sel.css('meta[name="title"]::attr(content)').get()
            or sel.css("h1::text").get()
        )

        #Preço pode estar em diversas combinações de classes
        fraction_text = (
            sel.css(".andes-money-amount__fraction::text").get()
            or sel.css(".price-tag-fraction::text").get()
        )
        cents_text = (
            sel.css(".andes-money-amount__cents::text").get()
            or sel.css(".price-tag-decimal::text").get()
        )

        value: Optional[str] = None
        if fraction_text:
            whole_part = re.sub(r"\D", "", fraction_text)
            value = whole_part
            if cents_text:
                decimal_part = re.sub(r"\D", "", cents_text)
                value = f"{value}.{decimal_part}"
        else:
            #Fallback para ``span[itemprop=`price`]``
            raw_price = (
                sel.css('span[itemprop="price"]::attr(content)').get()
                or sel.css('span[itemprop="price"]::text').get()
            )
            if raw_price:
                cleaned = re.sub(r"[^\d.,]", "", raw_price)
                if "," in cleaned and "." in cleaned:
                    cleaned = cleaned.replace(".", "").replace(",", ".")
                else:
                    cleaned = cleaned.replace(",", ".")
                value = cleaned or None

        currency_value = (
            sel.css('meta[itemprop="priceCurrency"]::attr(content)').get()
            or sel.css('meta[property="product:price:currency"]::attr(content)').get()
            or sel.css('meta[property="og:price:currency"]::attr(content)').get()
        )

        return {
            "name": title,
            "url": url,
            #Normaliza o valor monetário utilizando a função da classe base
            "current_price": self._format_price(value, currency_value),
        }


class AmazonHtmlStaticStrategy(HtmlStaticStrategy):
    """ Estratégia para páginas estáticas da Amazon Brasil """
    domain = "amazon.com.br"

    def _parse_html(self, html: str, url: str) -> dict:
        """ Extrai nome/preço (JSON-LD/meta) com fallbacks específicos da Amazon """
        structured = extract_structured_data(html, url)
        data = self._extract_from_structured_data(structured, url)
        if data.get("name") and data.get("current_price"):
            return data

        #Parsel first: tenta JSON-LD/meta
        sel = Selector(text=html)
        data = self._extract_from_json_ld_parsel(sel, url)
        if not data.get("name") or not data.get("current_price"):
            data = self._extract_from_meta_tags_parsel(sel, url)
        if data.get("name") and data.get("current_price"):
            return data

        #Fallback para BeautifulSoup(lxml)
        soup = BeautifulSoup(html, "lxml")

        #Primeiro tenta os extratores genéricos da classe base
        data = self._extract_from_json_ld(soup, url)
        if not data.get("name") or not data.get("current_price"):
            data = self._extract_from_meta_tags(soup, url)

        if data.get("name") and data.get("current_price"):
            return data

        # ---------- FALLBACK PARA SELETORES ESPECÍFICOS DA AMAZON (PARSEL) ----------
        #Título pode estar em ``#productTitle``, variações de ``id`` contendo "productTitle" (ignorando maiúsculas/minúsculas) ou em ``#title``; Os seletores XPath utilizam ``translate`` para normalizar o ``id``. 
        name = (
            sel.css("#productTitle::text").get()
            or sel.xpath("//span[contains(translate(@id, 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'producttitle')]/text()").get()
            or sel.xpath("//*[translate(@id, 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz')='title']/text()").get()
            or sel.css('meta[property="og:title"]::attr(content)').get()
        )

        #Preço pode aparecer em diversos locais dependendo do layout da página
        raw_price = (
            sel.css("#corePriceDisplay_desktop_feature_div span.a-offscreen::text").get()
            or sel.css(".apexPriceToPay span.a-offscreen::text").get()
            or sel.css("#priceblock_ourprice::text").get()
            or sel.css("#priceblock_dealprice::text").get()
            or sel.css("#priceblock_saleprice::text").get()
            or sel.css("#price_inside_buybox::text").get()
            or sel.css("#apex_desktop span.a-price > span.a-offscreen::text").get()
        )

        #Moeda pode estar em meta tags ou ser inserida do símbolo exibido
        currency: Optional[str] = sel.css('meta[property="og:price:currency"]::attr(content)').get()

        #Fallback para estruturas que dividem o valor em parte inteira e decimal
        if not raw_price:
            whole = sel.css("span.a-price-whole::text").get()
            fraction = sel.css("span.a-price-fraction::text").get()
            if whole:
                whole_part = re.sub(r"\D", "", whole)
                fraction_part = re.sub(r"\D", "", fraction) if fraction else "00"
                raw_price = f"{whole_part}.{fraction_part}"
                if not currency:
                    symbol = sel.css("span.a-price-symbol::text").get()
                    currency = symbol.strip() if symbol else None

        if not currency and raw_price:
            #Extrai símbolos não numéricos do início do preço (ex.: R$)
            symbol_match = re.match(r"[^\d]+", raw_price)
            currency = symbol_match.group(0).strip() if symbol_match else None

        #Limpa o valor numérico do preço removendo símbolos e separadores
        numeric_price: Optional[str] = None
        if raw_price:
            cleaned = re.sub(r"[^\d.,]", "", raw_price)
            if "," in cleaned and "." in cleaned:
                cleaned = cleaned.replace(".", "").replace(",", ".")
            else:
                cleaned = cleaned.replace(",", ".")
            numeric_price = cleaned or None

        return {
            "name": name,
            "url": url,
            #Normaliza o valor monetário utilizando a função da classe base
            "current_price": self._format_price(numeric_price, currency),
        }
    

class MagaluHtmlStaticStrategy(HtmlStaticStrategy):
    """ Estratégia para páginas estáticas do Magazine Luiza """
    domain = "magazineluiza.com.br"

    def _parse_html(self, html: str, url: str) -> dict:
        """ Extrai nome/preço (JSON-LD/meta) e usa fallbacks comuns do Magalu """
        structured = extract_structured_data(html, url)
        data = self._extract_from_structured_data(structured, url)
        if data.get("name") and data.get("current_price"):
            return data

        #Parsel first: tenta JSON-LD/meta
        sel = Selector(text=html)
        data = self._extract_from_json_ld_parsel(sel, url)
        if data.get("name") and data.get("current_price"):
            return data
        data = self._extract_from_meta_tags_parsel(sel, url)
        if data.get("name") and data.get("current_price"):
            return data

        #Fallback para BeautifulSoup(lxml)
        soup = BeautifulSoup(html, "lxml")

        #Tenta extrair via bloco JSON-LD específico de produto
        data = self._extract_from_json_ld(soup, url)
        if data.get("name") and data.get("current_price"):
            return data

        #Próxima tentativa é extrair meta-tags comuns em páginas do Magalu
        data = self._extract_from_meta_tags(soup, url)
        if data.get("name") and data.get("current_price"):
            return data

        #Incializa variáveis que poderão ser preenchidas pelos fallbacks
        name: Optional[str] = None
        price: Optional[str] = None

        #Ultimo recurso é estado inicial embutido em script
        script_tag = soup.find("script", string=re.compile("window.__INITIAL_STATE__"))
        if script_tag and script_tag.string:
            match = re.search(
                r"window.__INITIAL_STATE__\s*=\s*(\{.*?\})\s*;",
                script_tag.string,
                re.DOTALL,
            )
            if match:
                try:
                    state = json.loads(match.group(1))

                    #Busca recursiva por chaves relevantes
                    def _deep_search(obj: Any, keys: set[str]):
                        if isinstance(obj, dict):
                            for k, v in obj.items():
                                lk = k.lower()
                                if lk in keys and not isinstance(v, (dict, list)):
                                    return {lk: v}
                                found = _deep_search(v, keys)
                                if found:
                                    return found
                        elif isinstance(obj, list):
                            for item in obj:
                                found = _deep_search(item, keys)
                                if found:
                                    return found
                        return {}

                    name_dict = _deep_search(state, {"name", "title"})
                    price_dict = _deep_search(state, {"price", "pricevalue", "bestprice"})
                    if name_dict:
                        name = next(iter(name_dict.values()))
                    if price_dict:
                        price = next(iter(price_dict.values()))
                except json.JSONDecodeError:
                    #Se o JSON estiver malformado, o fallback é ignorado
                    pass

        return {
            "name": name,
            "url": url,
            #Normaliza o valor monetário utilizando a função da classe base
            "current_price": self._format_price(price, None),
        }


__all__ = [
    "HtmlStaticStrategy",
    "MercadoLivreHtmlStaticStrategy",
    "AmazonHtmlStaticStrategy",
    "MagaluHtmlStaticStrategy",
]
