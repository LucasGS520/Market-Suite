""" Utilitários de domínio para gestão de contas de usuários """

import phonenumbers
from fastapi import HTTPException, status


def normalize_email(value: str) -> str:
    """ Normaliza e-mail para comparação consistente e persistência """
    return value.strip().lower()

def normalize_phone(value: str | None) -> str | None:
    """ Normaliza telefone para E.164, formato usado pelo domínio de usuários """
    if not value:
        return None
    try:
        parsed = phonenumbers.parse(value, "BR")
    except phonenumbers.NumberParseException as exc:
        #O domínio converte erros técnicos em resposta de validação previsível.
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Telefone inválido") from exc
    if not phonenumbers.is_valid_number(parsed):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Telefone inválido")
    return phonenumbers.format_number(parsed, phonenumbers.PhoneNumberFormat.E164)
