""" Conversão e manipulação de valores monetários """

from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation


def _normalize_raw_price(raw: str) -> str:
    """ Remove símbolos e converte vírgula decimal para ponto """
    cleaned = re.sub(r"[^0-9,.-]", "", raw)
    if not cleaned:
        return ""
    if "," in cleaned and "." in cleaned:
        cleaned = cleaned.replace(".", "").replace(",", ".")
    elif cleaned.count(",") == 1 and cleaned.count(".") == 0:
        cleaned = cleaned.replace(",", ".")
    return cleaned

def parse_price_str(raw: str | int | float | Decimal, url: str) -> Decimal:
    """ Converte diferentes formatos de preço em ``Decimal`` 
    
    Aceita strings com símbolos brasileiros (``R$``), números simples ou
    objetos ``Decimal``. Levanta ``ValueError`` quando o conteúdo não pode
    ser interpretado.
    """
    if raw is None:
        raise ValueError(f"Preço não encontrado na página {url}")
    
    if isinstance(raw, Decimal):
        return raw
    if isinstance(raw, (int)):
        return Decimal(raw)
    if isinstance(raw, float):
        return Decimal(str(raw))
    
    raw_text = str(raw).strip()
    if not raw_text:
        raise ValueError(f"Preço não encontrado na página {url}")
    
    normalized = _normalize_raw_price(raw_text)
    if not normalized:
        raise ValueError(f"Preço não encontrado na página {url}")

    try:
        return Decimal(normalized)
    except InvalidOperation as exc:
        raise ValueError(f"Preço inválido em {url}: {raw_text}") from exc
    
__all__ = ["parse_price_str"]
