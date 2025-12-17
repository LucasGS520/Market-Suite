""" Heurísticas de disponibilidade e estado de anúncios

O módulo concentra detectores simples por domínio e um verificador
genérico para sinalizar quando um anúncio está pausado, removido ou
indisponível. As heurísticas priorizam mensagens textuais comuns e
códigos HTTP para evitar registrar preços nulos ou zerados no restante
da suíte.
"""

from __future__ import annotations
import re
from typing import Callable, Iterable, Tuple
import structlog
from shared.metrics.metrics_scraper import SCRAPER_AVAILABILITY_HEURISTICS_TOTAL


logger = structlog.get_logger("availability_detector")
DetectorResult = Tuple[bool, str, str]
DetectorCallable = Callable[[str], DetectorResult | None]

def _contains_any(haystack: str, needles: Iterable[str]) -> bool:
    """ Retorna ``True`` quando o texto contém qualquer termo fornecido """
    for needle in needles:
        if needle in haystack:
            return True
    return False

def _detect_meli(html: str) -> DetectorResult | None:
    """ Identifica banners de anúncio pausado ou indisponível no Mercado Livre"""
    if _contains_any(html, ("anúncio pausado", "anuncio pausado", "produto pausado")):
        return False, "paused", "meli_paused"
    if _contains_any(html, ("produto indisponível", "produto não disponível", "indisponível no momento")):
        return False, "unavailable", "meli_unavailable"
    return None

def _detect_amazon(html: str) -> DetectorResult | None:
    """ Verifica mensagens padrão de indisponibilidade na Amazon """
    if _contains_any(
        html,
        (
            "este item não está disponível",
            "item não disponível",
            "atualmente indisponível",
            "no momento este item está indisponível",
        ),
    ):
        return False, "unavailable", "amazon_unavailable"
    return None

def _detect_magalu(html: str) -> DetectorResult | None:
    """ Detecta páginas com selo de indisponibilidade do Magalu """
    if _contains_any(html, ("produto indisponível", "avise-me quando chegar", "avise-me", "esgotado")):
        return False, "unavailable", "magalu_unavailable"
    return None

def _detect_generic(html: str) -> DetectorResult | None:
    """ Aplica heurística genérica de indisponibilidade """
    if _contains_any(
        html,
        (
            "produto indisponível",
            "indisponível",
            "não disponível",
            "esgotado",
            "out of stock",
            "sold out",
            "produto removido",
        ),
    ):
        return False, "unavailable", "generic_unavailable"
    return None

def _detect_metadata_flags(html: str) -> DetectorResult | None:
    """ Verifica metadados padronizados de disponibilidade (schema/og) """
    #Observa padrões comuns em JSON-LD ou microdata sem parsing pesado
    if re.search(r"availability\"?\s*[:=]\s*\"?(?:outofstock|soldout)\"?", html):
        return False, "unavailable", "metadata_out_of_stock"

    if "og:availability" in html:
        if re.search(r"og:availability\"?\s+content=\"?out of stock\"?", html):
            return False, "unavailable", "metadata_og_out_of_stock"
        if re.search(r"og:availability\"?\s+content=\"?discontinued\"?", html):
            return False, "removed", "metadata_og_discontinued"

    return None

_DETECTORS: tuple[tuple[str, DetectorCallable], ...] = (
    ("mercadolivre.com.br", _detect_meli),
    ("mercadolivre.com", _detect_meli),
    ("amazon.com.br", _detect_amazon),
    ("amazon.com", _detect_amazon),
    ("magazineluiza.com.br", _detect_magalu),
    ("magazineluiza.com", _detect_magalu),
)

def _register_heuristic(reason: str, *, domain: str | None) -> None:
    """ Incrementa a métrica de heurísticas aplicadas """
    SCRAPER_AVAILABILITY_HEURISTICS_TOTAL.labels(reason=reason).inc()
    logger.info(
        "availability_heuristic_applied",
        domain=domain or "unknown",
        reason=reason,
    )

def detect_availability(
    html: str | None,
    *,
    status_code: int | None,
    domain: str | None,
) -> tuple[bool | None, str | None]:
    """ Tenta inferir disponibilidade e último estado conhecido do anúncio

    A função considera primeiro códigos HTTP definitivos (404/410) e
    depois aplica detectores específicos por domínio com base em
    mensagens textuais conhecidas. Quando nenhuma heurística é acionada
    retorna ``(None, None)`` indicando ausência de sinal.
    """
    if status_code in {404, 410}:
        _register_heuristic(f"http_status_{status_code}", domain=domain)
        return False, "removed"

    if not html:
        return None, None

    normalized_html = html.lower()
    normalized_domain = (domain or "").lower()

    metadata = _detect_metadata_flags(normalized_html)
    if metadata:
        availability, last_status, reason = metadata
        _register_heuristic(reason, domain=domain)
        return availability, last_status

    for suffix, detector in _DETECTORS:
        if normalized_domain.endswith(suffix):
            result = detector(normalized_html)
            if result:
                availability, last_status, reason = result
                _register_heuristic(reason, domain=domain)
                return availability, last_status

    generic = _detect_generic(normalized_html)
    if generic:
        availability, last_status, reason = generic
        _register_heuristic(reason, domain=domain)
        return availability, last_status

    return None, None


__all__ = ["detect_availability"]
