""" Inferência de disponibilidade para o pipeline de scraping

O módulo concentra heutísticas para inferir disponibilidade a partir de
status HTTP e conteúdo HTML, garantindo que precedência seja sempre
payload > inferência > validador conforme o contrato do scraper.
"""

from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Callable, Iterable, Literal, Tuple

import structlog


logger = structlog.get_logger("availability_inference")

HTTP_STATUS_UNAVAILABLE = {404, 410, 451} #Produto não existe
HTTP_STATUS_TEMPORARILY_UNAVAILABLE = {503} #Pode voltar
HTTP_STATUS_ACCESS_DENIED = {401, 403} #Bloqueado

DetectorResult = Tuple[bool, str, str]
DetectorCallable = Callable[[str], DetectorResult | None]

@dataclass(frozen=True)
class InferenceResult:
    """ Representa a inferência de disponibilidade baseada em HTTP """
    availability: bool | None
    last_status: str
    confidence: Literal["high", "medium", "low"]

def _contains_any(haystack: str, needles: Iterable[str]) -> bool:
    """ Retorna ``True`` quando o texto contém qualquer termo fornecido """
    for needle in needles:
        if needle in haystack:
            return True
    return False

def _detect_meli(html: str) -> DetectorResult | None:
    """ Identifica banners de anúncio pausado ou indisponível no Mercado Livre """
    if _contains_any(html, ("anúncio pausado", "produto não disponível", "indisponível no momento")):
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
    """ Detecta páginas com selo de indisponibilidade do Magazine Luiza """
    if _contains_any(html, ("produto indisponível", "avise-me quando chegar", "avise-me", "esgotado")):
        return False, "unavailable", "magalu_unavailable"
    return None

def _detect_generic(html: str) -> DetectorResult | None:
    """ Aplica heurísticas genérica de indisponibilidade """
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
    """ Verifica metadados padronizados de disponibilidade (schema/org) """
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
    ("generic", _detect_generic),
    ("metadata", _detect_metadata_flags),
)

def _register_heuristic(reason: str, *, domain: str | None) -> None:
    """ Registra em log a heurística aplicada """
    logger.info(
        "availability_heuristic_applied",
        domain=domain or "unknown",
        reason=reason,
    )

def infer_availability_from_http_status(status_code: int, domain: str) -> InferenceResult:
    """ Infere disponibilidade a partir do status HTTP da coleta

    Usa esta inferência quando não há payload válido e o erro HTTP indica
    claramente um anúncio removido, indisponível temporariamente ou bloqueio.
    A resposta é usada antes do validador, mas perde prioridade para o payload.
    """
    if status_code in HTTP_STATUS_UNAVAILABLE:
        _register_heuristic(f"http_status_{status_code}", domain=domain)
        return InferenceResult(availability=False, last_status="removed", confidence="high")
    
    if status_code in HTTP_STATUS_TEMPORARILY_UNAVAILABLE:
        _register_heuristic(f"http_status_{status_code}", domain=domain)
        return InferenceResult(availability=False, last_status="temporarily_unavailable", confidence="medium")
    
    if status_code in HTTP_STATUS_ACCESS_DENIED:
        _register_heuristic(f"http_status_{status_code}", domain=domain)
        return InferenceResult(availability=False, last_status="access_denied", confidence="medium")
    
    return InferenceResult(availability=None, last_status="unknown", confidence="low")

def detect_availability(
    html: str | None,
    *,
    status_code: int | None,
    domain: str | None,
) -> tuple[bool | None, str | None]:
    """ Tenta inferir disponibilidade e último estado conhecido do anúncio

    A função considera primeiro códigos HTTP definitivos e depois aplica
    detectores específicos por domínio com base em mensagens textuais
    conhecidas. Quando nenhuma heurística é acionada retorna ``(None, None)``.
    """
    if status_code is not None:
        inference = infer_availability_from_http_status(status_code, domain or "unknown")
        if inference.availability is not None:
            return inference.availability, inference.last_status
        
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


__all__ = [
    "InferenceResult",
    "HTTP_STATUS_UNAVAILABLE",
    "HTTP_STATUS_TEMPORARILY_UNAVAILABLE",
    "HTTP_STATUS_ACCESS_DENIED",
    "detect_availability",
    "infer_availability_from_http_status",
]