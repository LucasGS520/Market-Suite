import re

__all__ = ["canonicalize_ml_url", "is_product_url"]

from urllib.parse import urlparse
from app.utils.constants import PRODUCT_HOSTS

PRODUCT_RE = re.compile(r"MLB[-_]?(\d+)", re.IGNORECASE)


def canonicalize_ml_url(url: str) -> str | None:
    """ Retorna URL canônico do produto do Mercado Livre ou ``None``.

     A forma canônica é ``https://produto.mercadolivre.com.br/MLB-<ID>``.
    ``url`` deve ter ``mercadolivre.com.br`` no ``hostname`` e conter o ID
    do produto. Caso contrário, retorna ``None``.
    """
    parsed = urlparse(str(url))
    host = parsed.hostname or ""
    if "mercadolivre.com.br" not in host:
        return None

    match = PRODUCT_RE.search(str(url))
    if not match:
        return None

    product_id = match.group(1)
    return f"https://produto.mercadolivre.com.br/MLB-{product_id}"

def is_product_url(url: str) -> bool:
    """ Verifica se a URL corresponde a uma página de produto do Mercado Livre """
    host = urlparse(str(url)).hostname or ""
    return host in PRODUCT_HOSTS
