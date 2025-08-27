""" Validador simples para garantir a qualidade dos dados extraídos """

from typing import Iterable
from decimal import Decimal, InvalidOperation


class DataQualityValidator:
    """ Verifica consistência básica dos dados obtidos no parser """

    def __init__(self, mandatory_fields: Iterable[str] | None = None) -> None:
        #Apenas ``name`` e ``current_price`` são verificados
        self.mandatory_fields = list(mandatory_fields or [
            "name",
            "current_price",
        ])

    def _parse_price(self, value: str) -> Decimal:
        """ Converte texto monetário em ``Decimal`` """
        text = value.replace("R$", "").strip().replace(".", "").replace(",", ".")
        return Decimal(text)

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
