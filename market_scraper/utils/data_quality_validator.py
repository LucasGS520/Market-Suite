""" Validador simples para garantir a qualidade dos dados extraídos """

from typing import Iterable
from decimal import Decimal, InvalidOperation
import re


class DataQualityValidator:
    """ Verifica consistência básica dos dados obtidos no parser 
    
    O objetivo é interromper o pipeline o quanto antes quando valores
    essenciais estão ausentes ou apresentam formatos suspeitos, evitando
    que dados inválidos cheguem às camadas de comparação ou alerta.
    """
    def __init__(
        self,
        mandatory_fields: Iterable[str] | None = None,
        expected_currency: str | None = None,
    ) -> None:
        """ Inicializa o validador com campos obrigatórios e moeda esperada """
        #Apenas ``name`` e ``current_price`` são verificados por padrão
        self.mandatory_fields = list(
            mandatory_fields or [
                "name",
                "current_price",
            ]
        )
        #Moeda esperada, como ``R$`` ou ``US$``
        self.expected_currency = expected_currency

    def _parse_price(self, value: str) -> Decimal:
        """ Converte texto monetário em ``Decimal`` e validando a moeda quando configurado """
        #Verifica se o valor é negativo
        is_negative = "-" in value

        #Quando houver moeda configurada, comparar prefixo/símbolo do texto
        if self.expected_currency:
            match = re.match(r"\s*([^\d\s-]+)", value)
            currency = match.group(1).strip() if match else ""
            if currency != self.expected_currency:
                raise ValueError(f"Moeda diferente da esperada: {currency}")

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
