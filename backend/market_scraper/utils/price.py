""" Conversão e manipulação de valores monetários

O módulo prioriza estratégias robustas para interpretar diferentes
formatos de preços mantendo ``Decimal`` como tipo canônico. O
``price-parser`` é utilizado sempre como primeira tentativa para
uniformizar o parsing e registrar métricas de adoção.
"""

from __future__ import annotations

import re
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

from price_parser import Price

from shared.metrics.metrics_scraper import SCRAPER_PRICE_PARSER_USAGE_TOTAL


#Constante garante arredondamento consistente com duas casas decimais
_TWO_DECIMAL_QUANTIZE = Decimal("0.01")

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
    objetos ``Decimal``. Sempre tenta primeiro interpretar o valor usando
    ``price-parser`` para lidar com formatos mais complexos e registra o
    resultado em métricas, mantendo o fallback manual para garantir
    robustez. Lança ``ValueError`` quando conteúdo não pode ser
    interpretado.
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
    
    try:
        parsed_price = Price.fromstring(raw_text)
    except Exception:
        SCRAPER_PRICE_PARSER_USAGE_TOTAL.labels(outcome="error").inc()
    else:
        if parsed_price and parsed_price.amount is not None:
            try:
                candidate = Decimal(str(parsed_price.amount))
            except InvalidOperation:
                SCRAPER_PRICE_PARSER_USAGE_TOTAL.labels(outcome="invalid_amount").inc()
            else:
                SCRAPER_PRICE_PARSER_USAGE_TOTAL.labels(outcome="parsed").inc()
                return candidate.quantize(_TWO_DECIMAL_QUANTIZE, rounding=ROUND_HALF_UP)
            
        else:
            SCRAPER_PRICE_PARSER_USAGE_TOTAL.labels(outcome="missing_amount").inc()

    normalized = _normalize_raw_price(raw_text)
    if not normalized:
        raise ValueError(f"Preço não encontrado na página {url}")

    try:
        parsed = Decimal(normalized)
    except InvalidOperation as exc:
        raise ValueError(f"Preço inválido em {url}: {raw_text}") from exc
    #Registramos explicitamente quando o fallback manual foi necessário
    SCRAPER_PRICE_PARSER_USAGE_TOTAL.labels(outcome="fallback").inc()
    return parsed.quantize(_TWO_DECIMAL_QUANTIZE, rounding=ROUND_HALF_UP)
    
def format_decimal_to_str(value: Decimal) -> str:
    """ Formata ``Decimal`` com duas casas decimais para resposta padronizada """
    #Centraliza a formatação para manter arredondamento consistente
    quantized = value.quantize(_TWO_DECIMAL_QUANTIZE, rounding=ROUND_HALF_UP)
    return format(quantized, "f")

__all__ = ["parse_price_str", "format_decimal_to_str"]
