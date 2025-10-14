""" Conversão e manipulação de valores monetários 

O módulo prioriza estratégias robustas para interpretar diferentes 
formatos de preços mantendo ``Decimal`` como tipo canônico. A integração
com o ``price-parser`` é opcional e controlada por flag, garantindo
compatibilidade com o restante do pipeline.
"""

from __future__ import annotations

import re
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

from price_parser import Price

from market_scraper.core.config_scraper import settings
from shared.metrics.metrics_scraper import SCRAPER_PRICE_PARSER_USAGE_TOTAL

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
    objetos ``Decimal``. Quando habilitado, tenta primeiro interpretar o
    valor usando ``price-parser`` para lidar com formatos mais complexos e
    registra o resultado em métricas. mantém o comportamento anterior
    levantando ``ValueError`` quando conteúdo não pode ser interpretado.
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
    
    if settings.SCRAPER_USE_PRICE_PARSER:
        #Utiliza price-parser antes do fallback manual para cobrir formatos avançados
        try:
            parsed_price = Price.fromstring(raw_text)
        except Exception: #price-parser pode lançar erros internos em entradas incomuns
            SCRAPER_PRICE_PARSER_USAGE_TOTAL.labels(outcome="error").inc()
        else:
            if parsed_price and parsed_price.amount is not None:
                try:
                    candidate = Decimal(str(parsed_price.amount))
                except InvalidOperation:
                    SCRAPER_PRICE_PARSER_USAGE_TOTAL.labels(outcome="invalid_amount").inc()
                else:
                    SCRAPER_PRICE_PARSER_USAGE_TOTAL.labels(outcome="parsed").inc()
                    return candidate
            
            else:
                SCRAPER_PRICE_PARSER_USAGE_TOTAL.labels(outcome="missing_amount").inc()

    normalized = _normalize_raw_price(raw_text)
    if not normalized:
        raise ValueError(f"Preço não encontrado na página {url}")

    try:
        return Decimal(normalized)
    except InvalidOperation as exc:
        raise ValueError(f"Preço inválido em {url}: {raw_text}") from exc
    
def format_decimal_to_str(value: Decimal) -> str:
    """ Formata ``Decimal`` com duas casas decimais para resposta padronizada """
    #Centraliza a formatação para manter arredondamento consistente
    quantized = value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    return format(quantized, "f")

__all__ = ["parse_price_str", "format_decimal_to_str"]
