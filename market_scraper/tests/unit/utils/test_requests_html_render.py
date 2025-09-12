""" Testes para utilitário de renderização com Requests-HTML """

from unittest.mock import Mock, patch

from market_scraper.utils.requests_html_render import fetch_rendered_html


def test_fetch_rendered_html_renderiza_conteudo():
    """ Verifica se a função renderiza e retorna o HTML esperado """
    mock_html = Mock()
    mock_html.render = Mock()
    mock_html.html = "<div>teste</div>"

    mock_response = Mock()
    mock_response.html = mock_html
    
    session_mock = Mock()
    session_mock.get.return_value = mock_response

    with patch("market_scraper.utils.requests_html_render.HTMLSession", return_value=session_mock):
        html = fetch_rendered_html("http://exemplo.com")

    session_mock.get.assert_called_once_with("http://exemplo.com", timeout=20)
    mock_html.render.assert_called_once()
    session_mock.close.assert_called_once()
    assert html == "<div>teste</div>"
