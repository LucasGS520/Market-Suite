""" Valida a composição de headers realistas a partir dos perfis de User-Agent """

from market_scraper.core.config_scraper import settings
from market_scraper.utils.headers_profiles import compose_headers


def test_compose_headers_inclui_campos_basicos() -> None:
    """ Confirma que campos padronizados sempre acompanham o User-Agent """
    ua = settings.SCRAPER_USER_AGENT_STATIC_POOL[0]
    headers = compose_headers(ua)

    assert headers["User-Agent"] == ua
    assert headers["Accept"] == settings.SCRAPER_HEADERS_ACCEPT
    assert headers["Accept-Language"] == settings.SCRAPER_HEADERS_ACCEPT_LANGUAGE
    assert headers["Connection"] == settings.SCRAPER_HEADERS_CONNECTION
    assert headers["Cache-Control"] == "max-age=0"
    assert headers["Sec-Fetch-Dest"] == "document"

def test_compose_headers_chrome_inclui_client_hints() -> None:
    """ Chrome desktop deve conter client hints condizentes com a plataforma """
    chrome_ua = next(
        ua for ua in settings.SCRAPER_USER_AGENT_STATIC_POOL if "Chrome/" in ua and "Windows" in ua
    )
    headers = compose_headers(chrome_ua)

    assert headers["Sec-CH-UA-Mobile"] == "?0"
    assert headers["Sec-CH-UA-Platform"] == '"Windows"'
    assert "Google Chrome" in headers["Sec-CH-UA"]

def test_compose_headers_safari_mobile_nao_inclui_client_hints() -> None:
    """ Safari mobile não envia client hints adicionais """
    iphone_ua = next(ua for ua in settings.SCRAPER_USER_AGENT_STATIC_POOL if "iPhone" in ua)
    headers = compose_headers(iphone_ua)

    assert "Sec-CH-UA" not in headers
    assert "Sec-CH-UA-Platform" not in headers

def test_compose_headers_referer_e_resposta_isolada() -> None:
    """ Garantimos que Referer é opcional e que o dict retornado é isolado """
    ua = settings.SCRAPER_USER_AGENT_STATIC_POOL[0]
    referer = "https://exemplo.test/"

    headers_primeira_chamada = compose_headers(ua, referer=referer)
    headers_segunda_chamada = compose_headers(ua)

    assert headers_primeira_chamada["Referer"] == referer
    assert "Referer" not in headers_segunda_chamada
    headers_primeira_chamada["Accept"] = "alterado"
    assert headers_segunda_chamada["Accept"] == settings.SCRAPER_HEADERS_ACCEPT
    