""" Funções para renderizar páginas com JavaScript simples usando Requests-HTML """

from requests_html import HTMLSession


def fetch_rendered_html(url: str, timeout: int = 20, sleep: int = 1) -> str:
    """ Obtém o HTML pós-renderização de uma página.

    A função é indicada para cenários em que a página executa JavaScript
    leve para exibir o conteúdo desejado, evitando o custo de um
    navegador completo como o Playwright

    Parâmetros
    ----------
    url:
        Endereço da página que será coletada
    timeout:
        Tempo máximo em segundos para cada etapa da requisição e da renderização
    sleep:
        Intervalo adicional após a renderização para aguardar scripts tardios antes de retornar o HTML final.

    Retorna
    -------
    str
        O HTML final da página após a renderização básica do JavaScript.
    """
    session = HTMLSession()
    try:
        response = session.get(url, timeout=timeout)
        #Renderiza o JavaScript necessário sem abrir um navegador completo
        response.html.render(timeout=timeout, sleep=sleep)
        return response.html.html
    finally:
        session.close()
        