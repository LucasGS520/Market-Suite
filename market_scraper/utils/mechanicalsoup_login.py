""" Utilidades de login simples com MechanicalSoup

Este módulo fornece função auxiliar para fluxos de autenticação leves,
permitindo navegar por fomulários e capturar cookies de sessão sem
recorrer a navegadores pesados.
"""

from __future__ import annotations

import asyncio
from typing import Dict

import mechanicalsoup


async def login_and_get_cookies(config: Dict[str, str]) -> Dict[str, str]:
    """ Realiza login com MechanicalSoup e retorna cookies da sessão 
    
    Parâmetros
    ----------
    config: Dict[str, str]
        Dicionário com as informações necessárias para o login.
        As chaves esperadas são:
        - ``url``: página de autenticação.
        - ``form_selector``: seletor CSS do formulário de login.
        - ``fields``: pares ``nome: valor`` para preencher o formulário.

    Retorna
    -------
    Dict[str, str]
        Cookies obtidos após o envio do formulário, prontos para reutilização em requisições subsequentes.

    """
    def _sync_login() -> Dict[str, str]:
        browser = mechanicalsoup.StatefulBrowser()
        try:
            browser.open(config["url"])
            if config.get("form_selctor"):
                browser.select_form(config["form_selector"])
            for field, value in (config.get("fields") or {}).items():
                browser[field] = value
            browser.submit_selected()
            return browser.session.cookies.get_dict()
        finally:
            browser.close()

    return await asyncio.to_thread(_sync_login)    
