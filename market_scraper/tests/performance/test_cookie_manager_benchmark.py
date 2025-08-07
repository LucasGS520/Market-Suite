import requests

from scraper_app.utils.cookie_manager import CookieManager


def test_get_cookies_performance(benchmark):
    manager = CookieManager()
    benchmark(manager.get_cookies, "sess")

def test_update_from_response_performance(benchmark):
    manager = CookieManager()
    session = "sess"
    manager.get_cookies(session)
    resp = requests.Response()
    resp.cookies.set("session", "abc")
    benchmark(manager.update_from_response, session, resp)
