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
from urllib import robotparser

from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeoutError


OUTPUT_DIR = Path("debug_output")
OUTPUT_DIR.mkdir(exist_ok=True)


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
class DomProbe:
    url_final: str
    page_title: str
    html_length: int
    h1_count: int
    price_count: int
    json_ld_count: int
    anti_bot_detected: bool
    anti_bot_pattern: Optional[str]
    looks_like_product_page: bool
    classification: str
    classification_reason: str


@dataclass
class ProductData:
    name: Optional[str]
    current_price: Optional[str]
    currency: str = "BRL"
    availability: Optional[str] = None
    source: str = "mercadolivre"
    extraction_strategy: Optional[str] = None


@dataclass
class RunResult:
    timestamp_utc: str
    url_validation: dict[str, Any]
    dns_probe: dict[str, Any]
    robots_probe: dict[str, Any]
    acquisition: dict[str, Any]
    product: Optional[dict[str, Any]]


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
        allowed = rp.can_fetch(user_agent, url)
        return RobotsProbe(ok=True, robots_url=robots_url, can_fetch=allowed)
    except Exception as e:
        return RobotsProbe(ok=False, robots_url=robots_url, error=f"robots_probe_failed: {e}")


async def save_debug_artifacts(page, prefix: str) -> tuple[str, str]:
    screenshot_path = OUTPUT_DIR / f"{prefix}.png"
    html_path = OUTPUT_DIR / f"{prefix}.html"

    await page.screenshot(path=str(screenshot_path), full_page=True)
    html = await page.content()
    html_path.write_text(html, encoding="utf-8")

    return str(screenshot_path), str(html_path)


def detect_anti_bot(html: str) -> tuple[bool, Optional[str]]:
    html_lower = html.lower()
    for pattern in ANTI_BOT_PATTERNS:
        if pattern in html_lower:
            return True, pattern
    return False, None


def classify_dom(html: str, url_final: str, page_title: str, h1_count: int, price_count: int, json_ld_count: int) -> tuple[str, str, bool, Optional[str], bool]:
    anti_bot_detected, anti_bot_pattern = detect_anti_bot(html)
    looks_like_product_page = ("/p/" in url_final or "/up/" in url_final) and h1_count > 0

    if anti_bot_detected:
        return "ANTI_BOT", "HTML contains anti-bot signature", True, anti_bot_pattern, looks_like_product_page

    if len(html.strip()) < 1000:
        return "EMPTY_HTML", "HTML too short", False, None, looks_like_product_page

    if h1_count == 0 and price_count == 0 and json_ld_count == 0:
        return "NOT_PRODUCT_PAGE", "No product signals found in rendered DOM", False, None, looks_like_product_page

    if h1_count == 0:
        return "PARTIAL", "Rendered DOM has no h1", False, None, looks_like_product_page

    if price_count == 0 and json_ld_count == 0:
        return "PARTIAL", "Rendered DOM has title but no price signal", False, None, looks_like_product_page

    return "SUCCESS", "Rendered DOM looks usable for parsing", False, None, looks_like_product_page


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


async def extract_product(page, html: str) -> ProductData:
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


async def acquire_with_playwright(url: str, headless: bool = False) -> tuple[dict[str, Any], Optional[ProductData]]:
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=headless,
            slow_mo=150 if not headless else 0,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--disable-dev-shm-usage",
            ],
        )

        context = await browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/135.0.0.0 Safari/537.36"
            ),
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

            response = await page.goto(url, wait_until="domcontentloaded", timeout=60000)
            await page.wait_for_timeout(3500)

            html = await page.content()
            url_final = page.url
            page_title = await page.title()
            h1_count = await page.locator("h1").count()
            price_count = await page.locator(".andes-money-amount__fraction").count()
            json_ld_count = await page.locator("script[type='application/ld+json']").count()

            classification, reason, anti_bot_detected, anti_bot_pattern, looks_like_product_page = classify_dom(
                html=html,
                url_final=url_final,
                page_title=page_title,
                h1_count=h1_count,
                price_count=price_count,
                json_ld_count=json_ld_count,
            )

            screenshot_path, html_path = await save_debug_artifacts(page, "playwright_diagnostic")
            product = await extract_product(page, html)

            dom_probe = DomProbe(
                url_final=url_final,
                page_title=page_title,
                html_length=len(html),
                h1_count=h1_count,
                price_count=price_count,
                json_ld_count=json_ld_count,
                anti_bot_detected=anti_bot_detected,
                anti_bot_pattern=anti_bot_pattern,
                looks_like_product_page=looks_like_product_page,
                classification=classification,
                classification_reason=reason,
            )

            elapsed_ms = round((asyncio.get_running_loop().time() - started) * 1000, 2)
            acquisition = {
                "ok": classification in {"SUCCESS", "PARTIAL"},
                "http_status": response.status if response else None,
                "elapsed_ms": elapsed_ms,
                "layer_used": "browser",
                "fallback_taken": False,
                "dom_probe": asdict(dom_probe),
                "screenshot_path": screenshot_path,
                "html_path": html_path,
            }

            return acquisition, product

        except PlaywrightTimeoutError as e:
            elapsed_ms = round((asyncio.get_running_loop().time() - started) * 1000, 2)
            return {
                "ok": False,
                "http_status": None,
                "elapsed_ms": elapsed_ms,
                "layer_used": "browser",
                "fallback_taken": False,
                "error_code": "playwright_timeout",
                "error_message": str(e),
            }, None
        except Exception as e:
            elapsed_ms = round((asyncio.get_running_loop().time() - started) * 1000, 2)
            return {
                "ok": False,
                "http_status": None,
                "elapsed_ms": elapsed_ms,
                "layer_used": "browser",
                "fallback_taken": False,
                "error_code": "playwright_unexpected_error",
                "error_message": str(e),
            }, None
        finally:
            await context.close()
            await browser.close()


async def run_diagnostic(url: str, headless: bool = False, check_robots: bool = True) -> RunResult:
    validation = normalize_url(url)

    dns_probe = DNSProbe(False, validation.hostname or "", error="url_validation_failed")
    robots_probe = RobotsProbe(False, "", error="robots_not_checked")
    acquisition: dict[str, Any] = {"ok": False, "error_code": "not_started"}
    product: Optional[ProductData] = None

    if validation.ok:
        dns_probe = probe_dns(validation.hostname)
        if check_robots:
            robots_probe = probe_robots(validation.normalized_url)

        acquisition, product = await acquire_with_playwright(validation.normalized_url, headless=headless)

    return RunResult(
        timestamp_utc=utc_now_iso(),
        url_validation=asdict(validation),
        dns_probe=asdict(dns_probe),
        robots_probe=asdict(robots_probe),
        acquisition=acquisition,
        product=asdict(product) if product else None,
    )


async def main():
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
        result = await run_diagnostic(url, headless=False, check_robots=True)
        results.append(asdict(result))
        print(json.dumps(asdict(result), ensure_ascii=False, indent=2))

    output_file = OUTPUT_DIR / "diagnostic_results.json"
    output_file.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nResultados consolidados em: {output_file}")


if __name__ == "__main__":
    asyncio.run(main())
