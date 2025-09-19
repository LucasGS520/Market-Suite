from __future__ import annotations

""" Utilidades de parsing com Requests-HTML

Embora ``requests-html`` seja primariamente uma biblioteca para renderização
de JavaScript, ela também oferece seletores de alto nível.
O módulo fornece uma função dedicada para extrair nome e preço a partir
de um HTML já renderizado.

Exemplo
-------
>>> html = '''
... <html><head><meta property='og:title' content='Smartphone 5G' /></head>
... <body><span id='price'>R$ 4.299,00</span></body></html>
... '''
>>> parse_with_requests_html(html, url="https://loja.test/smartphone")
{'name': 'Smartphone 5G', 'current_price': 'R$ 4.299,00', 'url': 'https://loja.test/smartphone'}
"""

from requests_html import HTML


def _first_text(element) -> str:
    """ Extrai texto principal ou atributo ``content`` quando disponível """
    if element is None:
        return ""
    if element.attrs.get("content"):
        return element.attrs.get("content", "").strip()
    return element.text.strip()

def parse_with_requests_html(html: str, url: str | None = None) -> dict[str, str]:
    """ Extrai campos básicos a partir de conteúdo renderizado com ``requests-html`` 
    
    Parâmetros
    ----------
    html: str
        Conteúdo HTML bruto já processado (com ou sem renderização de JS)
    url: str | None
        Endereço da página analisada. Mantido para padronização da resposta.

    Retorna
    -------
    dict[str, str]
        Estrutura contendo ``name``, ``current_price`` e ``url`` da página analisada.
    """
    document = HTML(html=html, url=url)

    name = ""
    for selector in ["meta[property='og:title']", "meta[name='title']", "title", "h1"]:
        element = document.find(selector, first=True)
        name = _first_text(element)
        if name:
            break

    price = ""
    for selector in [
        "meta[itemprop='price']",
        "meta[property='product:price:amount']",
        "span#price",
        "span.price",
        "div.price",
    ]:
        element = document.find(selector, first=True)
        price = _first_text(element)
        if price:
            break

    return {
        "name": name,
        "current_price": price,
        "url": url or "",
    }


__all__ = ["parse_with_requests_html"]
