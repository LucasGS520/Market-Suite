""" Testes para funções de sanitização aplicadas e dados de scraping """

from shared.utils.text_sanitization import sanitize_media_url, sanitize_text


def test_sanitize_text_remove_tags_e_controles() -> None:
    """ Campos textuais devem ter tags removidas e controles descartados """
    value = "<script>alert('x')</script>Produto\x00"
    assert sanitize_text(value) == "alert('x')Produto"

def test_sanitize_text_trata_valores_nulos() -> None:
    """Valores vazios ou nulos devem resultar em ``None``"""
    assert sanitize_text(None) is None
    assert sanitize_text("   ") is None


def test_sanitize_media_url_aceita_http_https() -> None:
    """URLs de mídia devem ser normalizadas quando usam HTTP(s)"""
    assert sanitize_media_url("https://example.com/img.png#fragment") == "https://example.com/img.png"


def test_sanitize_media_url_rejeita_esquemas_perigosos() -> None:
    """Esquemas não suportados precisam ser descartados"""
    assert sanitize_media_url("javascript:alert('x')") is None
    assert sanitize_media_url("data:image/png;base64,aaaa") is None