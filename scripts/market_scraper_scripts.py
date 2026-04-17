import asyncio
import json
import re
import socket
import ipaddress
from dataclasses import dataclass, asdict, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Any
from urllib.parse import urlparse
from urllib import robotparser, request, error

from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeoutError

OUTPUT_DIR = Path("debug_output")
OUTPUT_DIR.mkdir(exist_ok=True)

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/135.0.0.0 Safari/537.36"
)

ANTI_BOT_PATTERNS = [
    "suspicious-traffic-frontend",
    "challenges.cloudflare.com",
    "__cf_chl",
    "__cf_bm",
    "recaptcha",
    "_pxcaptcha",
    "captcha",
    "access denied",
    "bot detection",
]

NAME_SELECTORS = [
    "h1.ui-pdp-title",
    "h1",
    "[data-testid='header-title']",
    "meta[property='og:title']",
]

PRICE_SELECTORS = [
    ".andes-money-amount__fraction",
    "[class*='money-amount'] .andes-money-amount__fraction",
    "[data-testid='price-part']",
    "meta[property='product:price:amount']",
]


@dataclass
class URLValidation:
    ok: bool
    original_url: str
    normalized_url: str
    scheme: str
    hostname: str
    error: Optional[str] = None


@dataclass
class DNSProbe:
    ok: bool
    hostname: str
    resolved_ips: list[str] = field(default_factory=list)
    public_ips: list[str] = field(default_factory=list)
    blocked_ips: list[str] = field(default_factory=list)
    error: Optional[str] = None


@dataclass
class RobotsProbe:
    ok: bool
    robots_url: str
    can_fetch: Optional[bool] = None
    error: Optional[str] = None


@dataclass
class FetchDecision:
    layer_selected: str
    reason: str
    http_attempted: bool
    browser_attempted: bool
    accepted_as_final: bool


@dataclass
class ProductData:
    name: Optional[str]
    current_price: Optional[str]
    currency: str = "BRL"
    availability: Optional[str] = None
    source: str = "mercadolivre"
    extraction_strategy: Optional[str] = None


@dataclass
class HTTPProbe:
    ok: bool
    status_code: Optional[int]
    final_url: Optional[str]
    html_length: int
    anti_bot_detected: bool
    anti_bot_pattern: Optional[str]
    looks_like_product_page: bool
    product_signals_found: bool
    classification: str
    classification_reason: str
    html_path: Optional[str] = None
    error: Optional[str] = None


@dataclass
class BrowserProbe:
    ok: bool
    status_code: Optional[int]
    final_url: Optional[str]
    page_title: Optional[str]
    html_length: int
    anti_bot_detected: bool
    anti_bot_pattern: Optional[str]
    looks_like_product_page: bool
    product_signals_found: bool
    classification: str
    classification_reason: str
    elapsed_ms: Optional[float] = None
    screenshot_path: Optional[str] = None
    html_path: Optional[str] = None
    error: Optional[str] = None


@dataclass
class RunResult:
    timestamp_utc: str
    url_validation: dict[str, Any]
    dns_probe: dict[str, Any]
    robots_probe: dict[str, Any]
    fetch_decision: dict[str, Any]
    http_probe: Optional[dict[str, Any]]
    browser_probe: Optional[dict[str, Any]]
    product: Optional[dict[str, Any]]
    final_status: str
    final_reason: str


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def normalize_url(url: str) -> URLValidation:
    raw = (url or "").strip()
    parsed = urlparse(raw)

    if not raw:
        return URLValidation(False, raw, raw, "", "", "empty_url")
    if parsed.scheme not in {"http", "https"}:
        return URLValidation(False, raw, raw, parsed.scheme, parsed.hostname or "", "invalid_scheme")
    if not parsed.hostname:
        return URLValidation(False, raw, raw, parsed.scheme, "", "missing_hostname")

    normalized = parsed._replace(fragment="").geturl()
    return URLValidation(True, raw, normalized, parsed.scheme, parsed.hostname, None)


def is_public_ip(ip: str) -> bool:
    obj = ipaddress.ip_address(ip)
    return not (
        obj.is_private
        or obj.is_loopback
        or obj.is_multicast
        or obj.is_link_local
        or obj.is_reserved
        or obj.is_unspecified
    )


def probe_dns(hostname: str) -> DNSProbe:
    try:
        infos = socket.getaddrinfo(hostname, None)
        ips = sorted({item[4][0] for item in infos})
        public_ips = [ip for ip in ips if is_public_ip(ip)]
        blocked_ips = [ip for ip in ips if ip not in public_ips]
        return DNSProbe(
            ok=len(public_ips) > 0,
            hostname=hostname,
            resolved_ips=ips,
            public_ips=public_ips,
            blocked_ips=blocked_ips,
            error=None if public_ips else "no_public_ip_resolved",
        )
    except socket.gaierror as e:
        return DNSProbe(False, hostname, error=f"dns_resolution_failed: {e}")
    except Exception as e:
        return DNSProbe(False, hostname, error=f"dns_probe_unexpected_error: {e}")


def probe_robots(url: str, user_agent: str = "*") -> RobotsProbe:
    parsed = urlparse(url)
    robots_url = f"{parsed.scheme}://{parsed.netloc}/robots.txt"
    rp = robotparser.RobotFileParser()
    rp.set_url(robots_url)
    try:
        rp.read()
        return RobotsProbe(ok=True, robots_url=robots_url, can_fetch=rp.can_fetch(user_agent, url))
    except Exception as e:
        return RobotsProbe(ok=False, robots_url=robots_url, error=f"robots_probe_failed: {e}")


def detect_anti_bot(html: str) -> tuple[bool, Optional[str]]:
    html_lower = html.lower()
    for pattern in ANTI_BOT_PATTERNS:
        if pattern in html_lower:
            return True, pattern
    return False, None


def has_product_signals(html: str, url_final: str) -> bool:
    html_lower = html.lower()
    return (
        "/p/" in url_final
        or "/up/" in url_final
        or 'application/ld+json' in html_lower
        or 'product:price:amount' in html_lower
        or 'ui-pdp-title' in html_lower
    )


def classify_html_common(html: str, url_final: str) -> tuple[str, str, bool, Optional[str], bool, bool]:
    anti_bot_detected, anti_bot_pattern = detect_anti_bot(html)
    looks_like_product_page = ("/p/" in url_final or "/up/" in url_final or "/_JM" in url_final)
    product_signals_found = has_product_signals(html, url_final)

    if anti_bot_detected and product_signals_found:
        return (
            "DEGRADED",
            "Anti-bot detected but product signals still exist",
            True,
            anti_bot_pattern,
            looks_like_product_page,
            product_signals_found,
        )

    if anti_bot_detected:
        return (
            "ANTI_BOT",
            "Anti-bot detected and product signals are weak",
            True,
            anti_bot_pattern,
            looks_like_product_page,
            product_signals_found,
        )

    if len(html.strip()) < 1000:
        return ("EMPTY_HTML", "HTML too short", False, None, looks_like_product_page, product_signals_found)

    if not product_signals_found:
        return (
            "NOT_PRODUCT_PAGE",
            "Product signals not found in HTML",
            False,
            None,
            looks_like_product_page,
            product_signals_found,
        )

    return ("SUCCESS", "HTML looks usable for parsing", False, None, looks_like_product_page, product_signals_found)


async def save_browser_artifacts(page, prefix: str) -> tuple[str, str, str]:
    screenshot_path = OUTPUT_DIR / f"{prefix}.png"
    html_path = OUTPUT_DIR / f"{prefix}.html"
    html = await page.content()
    await page.screenshot(path=str(screenshot_path), full_page=True)
    html_path.write_text(html, encoding="utf-8")
    return str(screenshot_path), str(html_path), html


def save_http_html(html: str, prefix: str) -> str:
    html_path = OUTPUT_DIR / f"{prefix}.html"
    html_path.write_text(html, encoding="utf-8")
    return str(html_path)


def normalize_price(raw: Optional[str]) -> Optional[str]:
    if not raw:
        return None
    cleaned = raw.replace("R$", "").replace("\xa0", " ").strip()
    cleaned = cleaned.replace(",", ".")
    match = re.search(r"\d[\d\.]*", cleaned)
    return match.group(0) if match else cleaned


def extract_json_ld_product(html: str) -> tuple[Optional[str], Optional[str], Optional[str]]:
    scripts = re.findall(
        r'<script[^>]*type=["\']application/ld\+json["\'][^>]*>(.*?)</script>',
        html,
        flags=re.IGNORECASE | re.DOTALL,
    )

    def walk(obj: Any) -> tuple[Optional[str], Optional[str], Optional[str]]:
        if isinstance(obj, dict):
            obj_type = obj.get("@type")
            if obj_type == "Product" or (isinstance(obj_type, list) and "Product" in obj_type):
                name = obj.get("name")
                offers = obj.get("offers")
                price = None
                availability = None
                if isinstance(offers, dict):
                    price = offers.get("price")
                    availability = offers.get("availability")
                elif isinstance(offers, list) and offers:
                    first = offers[0]
                    if isinstance(first, dict):
                        price = first.get("price")
                        availability = first.get("availability")
                return name, str(price) if price is not None else None, availability
            for value in obj.values():
                found = walk(value)
                if any(found):
                    return found
        elif isinstance(obj, list):
            for item in obj:
                found = walk(item)
                if any(found):
                    return found
        return None, None, None

    for script in scripts:
        try:
            data = json.loads(script)
        except Exception:
            continue
        found = walk(data)
        if any(found):
            return found
    return None, None, None


async def get_text_from_selector(page, selector: str, timeout: int = 3000) -> Optional[str]:
    locator = page.locator(selector).first
    try:
        await locator.wait_for(timeout=timeout)
        if selector.startswith("meta["):
            value = await locator.get_attribute("content")
            return value.strip() if value else None
        value = await locator.inner_text()
        return value.strip() if value else None
    except Exception:
        return None


async def get_first_text(page, selectors: list[str], timeout: int = 3000) -> tuple[Optional[str], Optional[str]]:
    for selector in selectors:
        text = await get_text_from_selector(page, selector, timeout=timeout)
        if text:
            return text, selector
    return None, None


async def extract_product_from_browser(page, html: str) -> ProductData:
    jsonld_name, jsonld_price, jsonld_availability = extract_json_ld_product(html)
    if jsonld_name or jsonld_price:
        return ProductData(
            name=jsonld_name,
            current_price=normalize_price(jsonld_price),
            availability=jsonld_availability or "unknown",
            extraction_strategy="json_ld",
        )

    name, name_selector = await get_first_text(page, NAME_SELECTORS, timeout=5000)
    raw_price, price_selector = await get_first_text(page, PRICE_SELECTORS, timeout=5000)
    strategy = None
    if name_selector or price_selector:
        strategy = f"dom::{name_selector or 'none'}::{price_selector or 'none'}"

    return ProductData(
        name=name,
        current_price=normalize_price(raw_price),
        availability="unknown",
        extraction_strategy=strategy,
    )


def extract_product_from_html(html: str) -> ProductData:
    jsonld_name, jsonld_price, jsonld_availability = extract_json_ld_product(html)
    return ProductData(
        name=jsonld_name,
        current_price=normalize_price(jsonld_price),
        availability=jsonld_availability or "unknown",
        extraction_strategy="json_ld" if (jsonld_name or jsonld_price) else None,
    )


def is_product_usable(product: Optional[ProductData]) -> bool:
    if not product:
        return False
    return bool(product.name and product.current_price)


def fetch_http_first(url: str, timeout_seconds: int = 12) -> tuple[HTTPProbe, Optional[ProductData]]:
    req = request.Request(
        url,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "pt-BR,pt;q=0.9,en-US;q=0.8,en;q=0.7",
        },
    )
    try:
        with request.urlopen(req, timeout=timeout_seconds) as resp:
            raw = resp.read()
            html = raw.decode("utf-8", errors="ignore")
            final_url = resp.geturl()
            status_code = getattr(resp, "status", None)
            html_path = save_http_html(html, "http_first_diagnostic")
            classification, reason, anti_bot_detected, anti_bot_pattern, looks_like_product_page, product_signals_found = classify_html_common(
                html, final_url
            )
            product = extract_product_from_html(html)
            ok = classification == "SUCCESS" and is_product_usable(product)
            probe = HTTPProbe(
                ok=ok,
                status_code=status_code,
                final_url=final_url,
                html_length=len(html),
                anti_bot_detected=anti_bot_detected,
                anti_bot_pattern=anti_bot_pattern,
                looks_like_product_page=looks_like_product_page,
                product_signals_found=product_signals_found,
                classification=classification,
                classification_reason=reason,
                html_path=html_path,
            )
            return probe, product if is_product_usable(product) else None
    except error.HTTPError as e:
        return HTTPProbe(
            ok=False,
            status_code=e.code,
            final_url=url,
            html_length=0,
            anti_bot_detected=False,
            anti_bot_pattern=None,
            looks_like_product_page=False,
            product_signals_found=False,
            classification="HTTP_ERROR",
            classification_reason=f"HTTP error: {e.code}",
            error=str(e),
        ), None
    except Exception as e:
        return HTTPProbe(
            ok=False,
            status_code=None,
            final_url=url,
            html_length=0,
            anti_bot_detected=False,
            anti_bot_pattern=None,
            looks_like_product_page=False,
            product_signals_found=False,
            classification="HTTP_FAILED",
            classification_reason="HTTP layer failed or returned unusable content",
            error=str(e),
        ), None


async def fetch_browser_fallback(url: str, headless: bool = False) -> tuple[BrowserProbe, Optional[ProductData]]:
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=headless,
            slow_mo=120 if not headless else 0,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--disable-dev-shm-usage",
            ],
        )
        context = await browser.new_context(
            user_agent=USER_AGENT,
            locale="pt-BR",
            viewport={"width": 1366, "height": 768},
            timezone_id="America/Sao_Paulo",
            java_script_enabled=True,
        )
        page = await context.new_page()
        started = asyncio.get_running_loop().time()
        try:
            await page.add_init_script(
                """
                Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
                Object.defineProperty(navigator, 'languages', { get: () => ['pt-BR', 'pt', 'en-US', 'en'] });
                Object.defineProperty(navigator, 'platform', { get: () => 'Win32' });
                Object.defineProperty(navigator, 'plugins', { get: () => [1, 2, 3, 4, 5] });
                """
            )
            response = await page.goto(url, wait_until="domcontentloaded", timeout=45000)
            await page.wait_for_timeout(2500)
            screenshot_path, html_path, html = await save_browser_artifacts(page, "browser_fallback_diagnostic")
            final_url = page.url
            title = await page.title()
            classification, reason, anti_bot_detected, anti_bot_pattern, looks_like_product_page, product_signals_found = classify_html_common(
                html, final_url
            )
            product = await extract_product_from_browser(page, html)
            ok = classification in {"SUCCESS", "DEGRADED"} and is_product_usable(product)
            elapsed_ms = round((asyncio.get_running_loop().time() - started) * 1000, 2)
            probe = BrowserProbe(
                ok=ok,
                status_code=response.status if response else None,
                final_url=final_url,
                page_title=title,
                html_length=len(html),
                anti_bot_detected=anti_bot_detected,
                anti_bot_pattern=anti_bot_pattern,
                looks_like_product_page=looks_like_product_page,
                product_signals_found=product_signals_found,
                classification=classification,
                classification_reason=reason,
                elapsed_ms=elapsed_ms,
                screenshot_path=screenshot_path,
                html_path=html_path,
            )
            return probe, product if is_product_usable(product) else None
        except PlaywrightTimeoutError as e:
            elapsed_ms = round((asyncio.get_running_loop().time() - started) * 1000, 2)
            return BrowserProbe(
                ok=False,
                status_code=None,
                final_url=url,
                page_title=None,
                html_length=0,
                anti_bot_detected=False,
                anti_bot_pattern=None,
                looks_like_product_page=False,
                product_signals_found=False,
                classification="TIMEOUT",
                classification_reason="Browser timed out",
                elapsed_ms=elapsed_ms,
                error=str(e),
            ), None
        except Exception as e:
            elapsed_ms = round((asyncio.get_running_loop().time() - started) * 1000, 2)
            return BrowserProbe(
                ok=False,
                status_code=None,
                final_url=url,
                page_title=None,
                html_length=0,
                anti_bot_detected=False,
                anti_bot_pattern=None,
                looks_like_product_page=False,
                product_signals_found=False,
                classification="BROWSER_FAILED",
                classification_reason="Browser layer failed",
                elapsed_ms=elapsed_ms,
                error=str(e),
            ), None
        finally:
            await context.close()
            await browser.close()


async def run_middle_ground_diagnostic(url: str, headless: bool = True, check_robots: bool = True) -> RunResult:
    validation = normalize_url(url)
    dns_probe = DNSProbe(False, validation.hostname or "", error="url_validation_failed")
    robots_probe = RobotsProbe(False, "", error="robots_not_checked")

    default_decision = FetchDecision(
        layer_selected="none",
        reason="not_started",
        http_attempted=False,
        browser_attempted=False,
        accepted_as_final=False,
    )

    if not validation.ok:
        return RunResult(
            timestamp_utc=utc_now_iso(),
            url_validation=asdict(validation),
            dns_probe=asdict(dns_probe),
            robots_probe=asdict(robots_probe),
            fetch_decision=asdict(default_decision),
            http_probe=None,
            browser_probe=None,
            product=None,
            final_status="FAIL",
            final_reason="URL inválida",
        )

    dns_probe = probe_dns(validation.hostname)
    if check_robots:
        robots_probe = probe_robots(validation.normalized_url)

    if not dns_probe.ok:
        return RunResult(
            timestamp_utc=utc_now_iso(),
            url_validation=asdict(validation),
            dns_probe=asdict(dns_probe),
            robots_probe=asdict(robots_probe),
            fetch_decision=asdict(default_decision),
            http_probe=None,
            browser_probe=None,
            product=None,
            final_status="FAIL",
            final_reason="DNS falhou antes da coleta",
        )

    http_probe, http_product = fetch_http_first(validation.normalized_url)

    if http_probe.ok and http_product:
        decision = FetchDecision(
            layer_selected="http",
            reason="HTTP trouxe HTML bom e dados confiáveis",
            http_attempted=True,
            browser_attempted=False,
            accepted_as_final=True,
        )
        return RunResult(
            timestamp_utc=utc_now_iso(),
            url_validation=asdict(validation),
            dns_probe=asdict(dns_probe),
            robots_probe=asdict(robots_probe),
            fetch_decision=asdict(decision),
            http_probe=asdict(http_probe),
            browser_probe=None,
            product=asdict(http_product),
            final_status="SUCCESS",
            final_reason="Sucesso pela camada HTTP",
        )

    browser_probe, browser_product = await fetch_browser_fallback(validation.normalized_url, headless=headless)

    if browser_probe.ok and browser_product:
        final_status = "SUCCESS" if browser_probe.classification == "SUCCESS" else "DEGRADED_SUCCESS"
        final_reason = (
            "Sucesso pelo browser com página limpa"
            if final_status == "SUCCESS"
            else "Sucesso pelo browser, mas com sinal de anti-bot"
        )
        decision = FetchDecision(
            layer_selected="browser",
            reason="HTTP falhou ou ficou fraco; browser conseguiu concluir",
            http_attempted=True,
            browser_attempted=True,
            accepted_as_final=True,
        )
        return RunResult(
            timestamp_utc=utc_now_iso(),
            url_validation=asdict(validation),
            dns_probe=asdict(dns_probe),
            robots_probe=asdict(robots_probe),
            fetch_decision=asdict(decision),
            http_probe=asdict(http_probe),
            browser_probe=asdict(browser_probe),
            product=asdict(browser_product),
            final_status=final_status,
            final_reason=final_reason,
        )

    decision = FetchDecision(
        layer_selected="browser",
        reason="Nem HTTP nem browser entregaram resultado confiável",
        http_attempted=True,
        browser_attempted=True,
        accepted_as_final=False,
    )
    return RunResult(
        timestamp_utc=utc_now_iso(),
        url_validation=asdict(validation),
        dns_probe=asdict(dns_probe),
        robots_probe=asdict(robots_probe),
        fetch_decision=asdict(decision),
        http_probe=asdict(http_probe),
        browser_probe=asdict(browser_probe),
        product=asdict(browser_product) if browser_product else None,
        final_status="FAIL",
        final_reason="Resultado final não foi confiável o suficiente",
    )


async def main() -> None:
    urls = [
        "https://www.mercadolivre.com.br/par-farol-hilux-sr-srv-2012-2013-2014-2015-pick-up-novo/up/MLBU3392951265?pdp_filters=item_id:MLB4186515547#is_advertising=true&searchVariation=MLBU3392951265&backend_model=search-backend&position=1&search_layout=stack&type=pad&tracking_id=89e56667-269f-4ac6-8300-147cf3467909&ad_domain=VQCATCORE_LST&ad_position=1&ad_click_id=ZDdmMzhhNjQtYWJhMi00NTU0LWE3MTQtNWM3NjZiYmNiMThl",
        "https://www.mercadolivre.com.br/par-lanterna-traseira-hyundai-hr-2004-2008-2009-2010-a-2017/up/MLBU781066028?pdp_filters=item_id:MLB4638119868#is_advertising=true&searchVariation=MLBU781066028&backend_model=search-backend&position=5&search_layout=grid&type=pad&tracking_id=c55c8831-ce07-4652-98b8-0a9703079c02&ad_domain=VQCATCORE_LST&ad_position=5&ad_click_id=N2FmODc4YzMtYjVkZi00NDc3LWExNWEtNjc1ZTJlMmQ3ZDky",
        "https://www.mercadolivre.com.br/parachoque-gol-g6-13-2014-2015-16--grades-sem-furo/up/MLBU1987454262?pdp_filters=item_id:MLB4205720230#is_advertising=true&searchVariation=MLBU1987454262&backend_model=search-backend&position=2&search_layout=stack&type=pad&tracking_id=24ba45df-8c13-4a08-bc9f-b3fb8226aacd&ad_domain=VQCATCORE_LST&ad_position=2&ad_click_id=Y2VmN2IxOTctZGNkZi00MGNmLWFiNDUtZDFlYzUwNmM1MDJk",
        "https://produto.mercadolivre.com.br/MLB-3542603997-farol-strada-2020-2021-2022-2023-_JM?searchVariation=181080252215#polycard_client=search-desktop&searchVariation=181080252215&search_layout=stack&position=5&type=item&tracking_id=e1bd7690-bf0c-42af-9134-e8385be57cd8",
        "https://produto.mercadolivre.com.br/MLB-4144250583-farol-dianteiro-strada-2020-2021-2022-2023-mascara-negra-_JM#polycard_client=recommendations_vip-pads-up&reco_backend=recomm_platform_base_pads_ron_marketplace&reco_model=rk_ent_v2_retsys_ads&reco_client=vip-pads-up&reco_item_pos=0&reco_backend_type=low_level&reco_id=263fdc53-33f5-4f14-a8c1-7c46b45af894&is_advertising=true&ad_domain=VIPDESKTOP_UP&ad_position=1&ad_click_id=ZWZlYjcwZDctZDgyNC00OWU0LTg0N2EtOGRjMTVhOWNmOTNm",
        "https://produto.mercadolivre.com.br/MLB-4598446581-par-farol-gol-2009-2010-2011-2012-fume-escuro-foco-duplo-amb-_JM#polycard_client=recommendations_vip-v2p&reco_backend=ranker_retrieval_online_vpp_v2p&reco_model=coldstart_low_exposition&reco_client=vip-v2p&reco_item_pos=2&reco_backend_type=low_level&reco_id=a6abf9ab-a2f0-45fe-8f2d-9e7eadb8c460&wid=MLB4598446581&sid=recos",
    ]

    results = []
    for url in urls:
        result = await run_middle_ground_diagnostic(url, headless=True, check_robots=True)
        payload = asdict(result)
        results.append(payload)
        print(json.dumps(payload, ensure_ascii=False, indent=2))

    output_file = OUTPUT_DIR / "middle_ground_results.json"
    output_file.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nResultados consolidados em: {output_file}")


if __name__ == "__main__":
    asyncio.run(main())
