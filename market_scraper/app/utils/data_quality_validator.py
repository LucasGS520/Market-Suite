""" Validador simples para garantir a qualidade dos dados extraídos """

import re
from typing import Iterable
from decimal import Decimal, InvalidOperation


class DataQualityValidator:
    """ Verifica consistência básica dos dados obtidos no parser """

    def __init__(self, mandatory_fields: Iterable[str] | None = None) -> None:
        self.mandatory_fields = list(mandatory_fields or [
            "name",
            "url",
            "current_price",
            "thumbnail",
            "seller"
        ])

    def _parse_price(self, value: str) -> Decimal:
        """ Converte texto monetário em ``Decimal`` """
        text = value.replace("R$", "").strip().replace(".", "").replace(",", ".")
        return Decimal(text)

    def validate(self, data: dict) -> None:
        """ Lança ``ValueError`` caso qualquer inconsistência for encontrado """
        for field in self.mandatory_fields:
            val = data.get(field)
            if val is None or str(val).strip() == "" or val in ("Não encontrado", "Não informado"):
                raise ValueError(f"Campo obrigatório ausente ou vazio: {field}")

        for price_field in ("current_price", "old_price"):
            val = data.get(price_field)
            if not val:
                if price_field == "current_price":
                    raise ValueError("Preço atual ausente")
                continue
            try:
                parsed = self._parse_price(str(val))
            except (InvalidOperation, AttributeError):
                raise ValueError(f"Preço inválido em {price_field}: {val}")
            if parsed <= 0:
                raise ValueError(f"Preço não positivo em {price_field}: {val}")

        shipping = str(data.get("shipping", ""))
        if shipping:
            patterns = [
                r"frete\s*(gr[áa]tis|pago)?",
                r"entrega\s*gr[áa]tis",
                r"gr[áa]tis",
                r"pago",
                r"não"
            ]
            if not any(re.search(p, shipping, re.I) for p in patterns):
                raise ValueError(f"Valor de shipping improvável: {shipping}")

        seller = str(data.get("seller", ""))
        if len(seller.strip()) < 2 or not any(c.isalpha() for c in seller):
            raise ValueError(f"Valor de seller improvável: {seller}")
