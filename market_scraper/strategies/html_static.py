from __future__ import annotations

""" Estratégia baseadas em HTML estático """

import json
import re
from decimal import Decimal
from typing import Any, Dict, Optional
from urllib.parse import urlparse

import asyncio
import httpx
import structlog
from bs4 import BeautifulSoup

from .base import ScrapingStrategy
from market_scraper.utils.constants import STEALTH_HEADERS, GENERIC_COOKIES
from market_scraper.utils.data_quality_validator import DataQualityValidator
from market_scraper.utils.user_agent_manager import IntelligentUserAgentManager
from market_scraper.utils.http_cache import get_cache_headers, store_cache_headers, ContentSignature, NOT_MODIFIED
from market_scraper.utils.robots_txt import RobotsTxtParser
from market_scraper.utils.throttle_manager import ThrottleManager


#Logger estruturado para acompanhar eventos de scraping
logger = structlog.get_logger(__name__)

class HtmlStaticStrategy(ScrapingStrategy):
    """ Estratégia genérica que realiza scraping em HTML estático

    A classe efetua uma requisição HTTP simples utilizando ``httpx`` com
    cabeçalhos de navegação realistas e cookies padrão definidos em
    ``STEALTH_HEADERS`` e ``GENERIC_COOKIES``. Em seguida tenta obter o
    nome e o preço do produto a partir de blocos ``JSON-LD`` (quando ``@type``
    é ``Product``). Caso esses dados não estejam presentes, é realizado um fallback
    para meta tags e seletores simples. Os campos resultantes são validados pelo
    ``DataQualityValidator``.
    """

    priority = 10
    domain: str = ""

    #Gerenciador de User-Agent para rotacionar cabeçalhos e minimizar bloqueios
    _ua_manager = IntelligentUserAgentManager()

    def supports_url(self, url: str) -> bool:
        """ Verifica se a URL pertence ao domínio esperado """
        netloc = urlparse(url).netloc
        return netloc.endswith(self.domain)

    async def _fetch_html(self, url: str) -> httpx.Response:
        """ Executa a requisição HTTP e retorna o ``httpx.Response`` obtido

        Antes de enviar a requisição são aplicados cabeçalhos realistas e o
        ``Referer`` dinâmico. Também são adicionados os valores de ``ETag`` e
        ``Last-Modified`` previamente armazenados para a URL, permitindo que o
        servidor retorne ``304 Not Modified`` quando o conteúdo não mudou.
        """
        parsed = urlparse(url)
        base_domain = f"{parsed.scheme}://{parsed.netloc}/"
        headers = {**STEALTH_HEADERS, "Referer": base_domain}
        #Utiliza o User-Agent previamente selecionado ou gera um novo
        headers["User-Agent"] = getattr(
            self,
            "_pending_ua",
            self._ua_manager.get_user_agent("html_static"),
        )

        #Recupera valores de cache para condicionar a requisição
        cache_headers = get_cache_headers(url)
        if cache_headers.get("etag"):
            headers["If-None-Match"] = cache_headers["etag"]
        if cache_headers.get("last_modified"):
            headers["If-Modified-Since"] = cache_headers["last_modified"]

        async with httpx.AsyncClient(
            headers=headers,
            cookies=GENERIC_COOKIES,
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


    def _extract_from_json_ld(self, soup: BeautifulSoup, url: str) -> dict:
        """ Procura blocos JSON-LD de produto e extrai informações principais

        A função também trata estruturas onde ``offers`` contém outra lista
        ``offers`` (caso comum em ``AggregateOffer``) e utiliza os campos
        ``lowPrice`` ou ``highPrice`` quando ``price`` estiver ausente.
        """
        for tag in soup.find_all("script", type="application/ld+json"):
            try:
                content = json.loads(tag.string or "{}")
            except json.JSONDecodeError:
                continue
            itens: list[Any]
            if isinstance(content, dict):
                itens = content.get("@graph", []) if "@graph" in content else [content]
            elif isinstance(content, list):
                itens = content
            else:
                itens = []
            for item in itens:
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
                    return {
                        "name": name,
                        "url": url,
                        "current_price": self._format_price(price, currency),
                    }
        return {}

    def _extract_from_meta_tags(self, soup: BeautifulSoup, url: str) -> dict:
        """ Extrai dados de meta-tags como alternativa ao JSON-LD """
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

        return {
            "name": name_value,
            "url": url,
            "current_price": self._format_price(
                price.get("content") if price else None,
                currency.get("content") if currency else None,
            )
        }

    def _parse_html(self, html: str, url: str) -> dict:
        """ Orquestra a extração dos dados do HTML informado """
        soup = BeautifulSoup(html, "html.parser")
        data = self._extract_from_json_ld(soup, url)
        if not data or not data.get("name"):
            data = self._extract_from_meta_tags(soup, url)
        return data

    async def get_data(self, url: str, headers: Optional[Dict[str, str]] = None, **kwargs: Any) -> dict:
        """ Executa o scraping e trata falhas de validação dos dados

        Em caso de falha na requisição, o método registra o status HTTP,
        o cabeçalho ``Location`` (quando presente) e um trecho do corpo
        da resposta. Além disso, quando o domíno alvo retorna **HTTP 403**
        o bloqueio é registrado no ``recovery_manager`` e o status
        ``blocked`` é informado ao chamador. A mensagem de detalhe inclui
        o domínio de origem para auxiliar a identificação do bloqueio.
        Também aguarda a liberação do ``ThrottleManager`` antes de cada
        requisição HTML, evitando excesso de chamadas.
        """
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
            resp = await self._fetch_html(url)
            #Suporte a testes que retornam apenas string em ``_fetch_html``
            if not isinstance(resp, httpx.Response):
                resp = httpx.Response(200, text=str(resp))
        except httpx.HTTPError as exc:
            #Registra detalhes da resposta para facilitar depuração
            resp = getattr(exc, "response", None)
            location = resp.headers.get("location") if resp else None
            body = resp.text[:200] if resp and resp.text else None
            logger.exception("Falha na requisição HTML", url=url, status=getattr(resp, "status_code", None), location=location, body=body)
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
        """ Extrai nome e preço de páginas do Mercado Livre

        A função inicia tentando os métodos genéricos de extração
        (JSON-LD e meta tags). Caso não obtenha os dados essenciais,
        realiza um fallback utilizando seletores específicos do site.
        """
        soup = BeautifulSoup(html, "html.parser")

        #Primeiro tenta reutilizar os extratores da estratégia base
        data = self._extract_from_json_ld(soup, url)
        if not data.get("name") or not data.get("current_price"):
            data = self._extract_from_meta_tags(soup, url)

        #Se já houver nome e preço válidos, retorna imediatamente
        if data.get("name") and data.get("current_price"):
            return data

        # --- FALLBACK PARA SELETORES ESPECÍFICOS DO MERCADO LIVRE ---

        #Título do produto em h1.ui-pdp-title ou meta[name="title"]
        #Como último recurso utiliza ``soup.find(`h1`)`` caso as alternativas específicas não estejam presentes
        title_tag = soup.select_one("h1.ui-pdp-title")
        meta_title = soup.find("meta", attrs={"name": "title"})
        generic_h1 = soup.find("h1") if not title_tag and not meta_title else None
        title: Optional[str] = None
        if title_tag:
            title = title_tag.get_text(strip=True)
        elif meta_title:
            title = meta_title.get("content")

        elif generic_h1:
            title = generic_h1.get_text(strip=True)

        #Preço pode estar em diversas combinações de classes
        fraction = (
            soup.select_one(".andes-money-amount__fraction")
            or soup.select_one(".price-tag-fraction")
            or soup.find("span", {"class": "price-tag-fraction"})
        )
        cents = (
            soup.select_one(".andes-money-amount__cents")
            or soup.select_one(".price-tag-decimal")
        )

        value: Optional[str] = None
        if fraction:
            #Remove separadores de milhar e outros caracteres da parte inteira
            whole_part = re.sub(r"\D", "", fraction.get_text())
            value = whole_part
            if cents:
                decimal_part = re.sub(r"\D", "", cents.get_text())
                #Concatena parte inteira e decimal para formar o valor
                value = f"{value}.{decimal_part}"

        else:
            #Fallback para ``span[itemprop=`price`]`` caso não exista estrutura de fração/centavos
            itemprop_price = soup.find("span", itemprop="price")
            if itemprop_price:
                raw_price = itemprop_price.get("content") or itemprop_price.get_text(strip=True)
                cleaned = re.sub(r"[^\d.,]", "", raw_price)
                if "," in cleaned and "." in cleaned:
                    cleaned = cleaned.replace(".", "").replace(",", ".")
                else:
                    cleaned = cleaned.replace(",", ".")
                value = cleaned or None

        #Busca a moeda em meta tags específicas caso esteja disponível
        currency_tag = (
            soup.find("meta", itemprop="priceCurrency")
            or soup.find("meta", property="product:price:currency")
            or soup.find("meta", property="og:price:currency")
        )
        currency_value = currency_tag.get("content") if currency_tag else None

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
        """ Extrai nome e preço das páginas de produto da Amazon

        O processo reutiliza os extratores genéricos de JSON-LD e meta
        tags. Quando esses não fornecerem ``name`` ou ``current_price``,
        realiza um fallback com seletores específicos da Amazon,
        considerando variações comuns de estrutura.
        """

        soup = BeautifulSoup(html, "html.parser")

        #Primeiro tenta os extratores genéricos da classe base
        data = self._extract_from_json_ld(soup, url)
        if not data.get("name") or not data.get("current_price"):
            data = self._extract_from_meta_tags(soup, url)

        #Caso já tenha obtido nome e preço, retorna imediatamente
        if data.get("name") and data.get("current_price"):
            return data

        # ---------- FALLBACK PARA SELETORES ESPECÍFICOS DA AMAZON ----------
        #Título pode estar em ``#productTitle``, ``span[id*=`productTitle`]`` ou ``#title``
        #Prioriza ``#productTitle`` > ``#title`` > ``<meta property="og:title">``
        title_tag = (
            soup.find(id=re.compile("^productTitle$", re.I))
            or soup.find("span", id=re.compile("productTitle", re.I))
            or soup.find(id=re.compile("^title$", re.I))
            or soup.find("meta", property="og:title")
        )
        name: Optional[str] = None
        if title_tag:
            #Meta tags guardam o conteúdo no atributo ``content``
            name = (
                title_tag.get("content")
                if title_tag.name == "meta"
                else title_tag.get_text(strip=True)
            )

        #Preço pode aparecer em diversos locais dependendo do layout da página
        price_tag = (
            soup.select_one("#corePriceDisplay_desktop_feature_div span.a-offscreen")
            or soup.select_one(".apexPriceToPay span.a-offscreen")
            #Fallback para outros seletores conhecidos apenas se o principal falhar
            or soup.find(id="priceblock_ourprice")
            or soup.find(id="priceblock_dealprice")
            or soup.find(id="priceblock_saleprice")
            or soup.find(id="price_inside_buybox")
            or soup.select_one("#apex_desktop span.a-price > span.a-offscreen")
        )
        raw_price = price_tag.get_text(strip=True) if price_tag else None

        #Moeda pode estar em meta tags ou ser inserida do símbolo exibido
        currency_tag = soup.find("meta", property="og:price:currency")
        currency: Optional[str] = currency_tag.get("content") if currency_tag else None

        #Fallback para estruturas que dividem o valor em parte inteira e decimal
        if not raw_price:
            whole = soup.select_one("span.a-price-whole")
            fraction = soup.select_one("span.a-price-fraction")
            if whole:
                #Remove caracteres não numéricos e combina as partes
                whole_part = re.sub(r"\D", "", whole.get_text())
                fraction_part = re.sub(r"\D", "", fraction.get_text()) if fraction else "00"
                raw_price = f"{whole_part}.{fraction_part}"
                if not currency:
                    symbol = soup.select_one("span.a-price-symbol")
                    currency = symbol.get_text(strip=True) if symbol else None

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


class ShopeeHtmlStaticStrategy(HtmlStaticStrategy):
    """ Estratégia para páginas estáticas da Shopee """
    domain = "shopee.com.br"

    def _parse_html(self, html: str, url: str) -> dict:
        """ Extrai dados de nome e preço específicos da Shopee

        A rotina procura inicialmente pelo script ``<script id="__NEXT_DATA__">``
        que contém um JSON com o estado completo da página. A partir desse JSON é
        feita uma busca recursiva dentro de ``props.pageProps`` para localizar
        campos de nome e preço do produto. Se qualquer etapa falhar, os métodos
        genéricos de extração da classe base são utilizados como fallback
        """

        soup = BeautifulSoup(html, "html.parser")

        #Primeiro tenta JSON embutido em __NEXT_DATA__
        script_tag = soup.find("script", id="__NEXT_DATA__")
        if script_tag and script_tag.string:
            try:
                data = json.loads(script_tag.string)
                page_props = data.get("props", {}).get("pageProps", {})

                #Busca recursiva por chaves relevantes dentro de ``pageProps``
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

                name_dict = _deep_search(page_props, {"name", "title"})
                #Inclui chaves alternativas utilizadas pela shopee para representar preços
                price_dict = _deep_search(
                    page_props,
                    {
                        "price",
                        "pricedisplay",
                        "amount",
                        "price_min",
                        "price_before_discount",
                        "price_min_before_discount",
                    },
                )
                currency_dict = _deep_search(page_props, {"currency", "currencysymbol"})

                name = next(iter(name_dict.values())) if name_dict else None
                price = next(iter(price_dict.values())) if price_dict else None
                currency = next(iter(currency_dict.values())) if currency_dict else None

                #Normaliza o preço encontrado para facilitar a conversão monetária
                if isinstance(price, str):
                    cleaned = re.sub(r"[^\d.,]", "", price)
                    if "," in cleaned and "." in cleaned:
                        cleaned = cleaned.replace(".", "").replace(",", ".")
                    else:
                        cleaned = cleaned.replace(",", ".")
                    price = cleaned or None

                elif isinstance(price, int):
                    #Valores inteiros costumam representar o preço multiplicado por 100000
                    price = Decimal(price) / Decimal("100000")

                if name and price is not None:
                    return {
                        "name": name,
                        "url": url,
                        "current_price": self._format_price(price, currency),
                    }
            except json.JSONDecodeError:
                pass

        # ---------- FALLBACK UTILIZA EXTRATORES GENÉRICOS DE CLASSE BASE ----------
        data = self._extract_from_json_ld(soup, url)
        if not data.get("name") or not data.get("current_price"):
            data = self._extract_from_meta_tags(soup, url)
        return data


class MagaluHtmlStaticStrategy(HtmlStaticStrategy):
    """ Estratégia para páginas estáticas do Magazine Luiza """
    domain = "magazineluiza.com.br"

    def _parse_html(self, html: str, url: str) -> dict:
        """ Extrai nome e preço das páginas do Magazine Luiza

        Retorna sempre um dicionário contendo ``name`` e ``current_price``.
        Caso algum valor não seja localizado, o campo correspondente será
        ``None`` ou vazio, permitindo que ``DataQualityValidator`` da classe
        sinalize inconsistência.
        """

        soup = BeautifulSoup(html, "html.parser")

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
    "ShopeeHtmlStaticStrategy",
    "MagaluHtmlStaticStrategy",
]
