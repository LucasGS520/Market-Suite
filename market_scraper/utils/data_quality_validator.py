""" Validador simples para garantir a qualidade dos dados extraídos """

from typing import Iterable
from decimal import Decimal, InvalidOperation
import re

from humanize import thousands_separator
from numpy.f2py.symbolic import normalize
from pydantic_core.core_schema import decimal_schema


class DataQualityValidator:
    """ Verifica consistência básica dos dados obtidos no parser """

    def __init__(self, mandatory_fields: Iterable[str] | None = None) -> None:
        #Apenas ``name`` e ``current_price`` são verificados
        self.mandatory_fields = list(mandatory_fields or [
            "name",
            "current_price",
        ])

    def _parse_price(self, value: str) -> Decimal:
        """ Converte texto monetário em ``Decimal``, aceitando múltiplas moedas """
        #Verifica se o valor é negativo
        is_negative = "-" in value

        #Remove caracteres que não sejam dígitos ou separadores de milhar/decimal
        cleaned = re.sub(r"[^0-9,\.]+", "", value)

        #Determina qual caractere é separador decimal
        if "," in cleaned and "." in cleaned:
            #O último separador encontrado é considerado o separador decimal
            decimal_sep = "," if cleaned.rfind(",") > cleaned.rfind(".") else "."
            thousands_sep = "." if decimal_sep == "," else ","
        elif "," in cleaned:
            decimal_sep = ","
            thousands_sep = ""
        elif "." in cleaned:
            decimal_sep = "."
            thousands_sep = ""
        else:
            decimal_sep = "."
            thousands_sep = ""

        #Remove separadores de milhar e normaliza o separador decimal para ponto
        normalized = cleaned.replace(thousands_sep, "").replace(decimal_sep, ".")
        amount = Decimal(normalized)
        return -amount if is_negative else amount

    def validate(self, data: dict) -> None:
        """ Lança ``ValueError`` caso qualquer inconsistência for encontrado """
        #Verifica presença e preenchimento dos campos obrigatórios
        for field in self.mandatory_fields:
            val = data.get(field)
            if val is None or str(val).strip() == "" or val in ("Não encontrado", "Não informado"):
                raise ValueError(f"Campo obrigatório ausente ou vazio: {field}")

        #Validação do preço atual
        val = data.get("current_price")
        try:
            parsed = self._parse_price(str(val))
        except (InvalidOperation, AttributeError):
            raise ValueError(f"Preço inválido em current_price: {val}")
        if parsed <= 0:
            raise ValueError(f"Preço não positivo em current_price: {val}")
