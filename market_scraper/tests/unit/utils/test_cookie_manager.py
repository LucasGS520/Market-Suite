import requests

from scraper_app.utils.cookie_manager import CookieManager
from scraper_app.utils.constants import GENERIC_COOKIES

def test_cookie_manager_persists_and_updates():
    """ Valida persistência e atualização de cookies por sessão """
    cm = CookieManager()
    session_id = "s1"

    #Cookies iniciais vindos de GENERIC_COOKIES
    jar = cm.get_cookies(session_id)
    for k, v in GENERIC_COOKIES.items():
        assert jar.get(k) == v

    #Resposta fake adicionando nono cookie
    resp = requests.Response()
    resp.status_code = 200
    resp._content = b""
    resp.cookies.set("session", "abc")

    cm.update_from_response(session_id, resp)

    jar2 = cm.get_cookies(session_id)
    assert jar2.get("session") == "abc"

    #Verifica se o cookie permanece em chamadas posteriores
    assert cm.get_cookies(session_id).get("session") == "abc"

def test_cookie_manager_is_per_session():
    """ Garante que cookies não vazam entre diferentes sessões """
    cm = CookieManager()
    jar1 = cm.get_cookies("a")
    jar1.set("foo", "bar")

    cm.update_from_response("a", requests.Response())

    jar2 = cm.get_cookies("b")
    assert jar2.get("foo") is None
    assert cm.get_cookies("a").get("foo") == "bar"
