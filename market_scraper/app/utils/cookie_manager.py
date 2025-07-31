""" Gerencia cookies de navegação separados por sessão de scraping """

from typing import Dict
from requests import Response, cookies
import httpx

from app.utils.constants import GENERIC_COOKIES


class CookieManager:
    """ Armazena cookies de forma simples por sessão """
    def __init__(self) -> None:
        self._store: Dict[str, cookies.RequestsCookieJar] = {}

    def get_cookies(self, session_id: str) -> cookies.RequestsCookieJar:
        """ Retorna os cookies de uma sessão, criando a partir de GENERIC_COOKIES se não existir """
        jar = self._store.get(session_id)
        if jar is None:
            jar = cookies.cookiejar_from_dict(GENERIC_COOKIES.copy())
            self._store[session_id] = jar
        return jar

    def update_from_response(self, session_id: str, response: Response | httpx.Response) -> None:
        """ Atualiza os cookies armazenados a partir de uma resposta HTTP """
        if response is None:
            return
        jar = self.get_cookies(session_id)
        jar.update(response.cookies)

    def reset(self, session_id: str | None = None) -> None:
        """ Limpa os cookies armazenados de uma sessão ou de todas """
        if session_id is None:
            self._store.clear()
        else:
            self._store.pop(session_id, None)

#Instância global utilizada pelos serviços
cookie_manager = CookieManager()
