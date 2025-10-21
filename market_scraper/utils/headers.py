""" Função utilitaria para composição de headers HTTP do scraper

O módulo concentra rotinas compartilhadas pela pipeline principal e por 
scripts auciliares ao montar cabeçalhos consistentes. Manter a lógica
em um único ponto reduz divergências quando o template de ``Referer``
muda ou recebe novos placeholders.
"""

from __future__ import annotations

from typing import Optional
from urllib.parse import urlparse

from structlog.typing import BindableLogger

from market_scraper.core.config_scraper import settings
from shared.utils.logging_utils import sanitize_log_data


REFERER_TEMPLATE_ERROR_EVENT = "referer_template_error"

def build_referer(
    url: str,
    *,
    logger: Optional[BindableLogger] = None,
    event_name: str = REFERER_TEMPLATE_ERROR_EVENT,
) -> str | None:
    """ Constrói o header ``Referer`` respeitando o template configurado
    
    A função utiliza o template definido em configuração para interpolar o
    domínio e a URL atuais. Em caso de template ausente ou inválido,
    retornamos ``None`` para que os chamadores mantenham o comportamento
    tolerante esperado. Quando um ``logger`` é fornecido, registramos o
    incidente utilizando o ``event_name`` informado para facilitar a
    correlação com métricas de rede.
    """
    template = settings.SCRAPER_HEADERS_REFERER_TEMPLATE
    if not template:
        return None
    
    domain = urlparse(url).hostname
    if not domain:
        return None
    
    try:
        return template.format(domain=domain, url=url)
    except Exception as exc:
        if logger is not None:
            logger.warning(
                event_name,
                template=sanitize_log_data(template),
                url=sanitize_log_data(url),
                error=sanitize_log_data(str(exc)),
            )
        return None
    
__all__ = ["build_referer", "REFERER_TEMPLATE_ERROR_EVENT"]
