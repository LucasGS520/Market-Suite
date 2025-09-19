""" Testes para o módulo ``market_scraper.parsers.selectorlib`` """

from pathlib import Path
import textwrap

import pytest

from market_scraper.parsers.selectorlib import load_selectorlib_extractor, parse_with_selectorlib


def test_parse_with_selectorlib(tmp_path: Path) -> None:
    """ Deve utilizar o template para extrair nome e preço """
    template = tmp_path / "produto.yaml"
    template.write_text(
        textwrap.dedent(
            """
            name:
              css: h1
              type: Text
            current_price:
              css: span.price
              type: Text
            """
        ).strip(),
        encoding="utf-8",
    )

    html = """
    <html><body>
    <h1>Placa de vídeo</h1>
    <span class="price">3999.99</span>
    </body></html>
    """

    extractor = load_selectorlib_extractor(template)
    resultado = parse_with_selectorlib(html, "https://loja.test/placa_video", extractor)

    assert resultado == {
        "name": "Placa de vídeo",
        "current_price": "3999.99",
        "url": "https://loja.test/placa_video",
    }

def test_parse_with_selectorlib_sem_template() -> None:
    """ Deve falhar quando nenhum template ou extractor é informado """
    with pytest.raises(ValueError):
        parse_with_selectorlib("<html></html>")
        