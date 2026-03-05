""" Validação de contatos de canal (email e telefone).

Funções puras — sem I/O, sem efeitos colaterais.
"""

from __future__ import annotations

import re

from email_validator import EmailNotValidError
from email_validator import validate_email as _validate_email_lib


def validate_email(value: str | None) -> bool:
    """ Valida se o email segue formato correto e parseável.

    Args:
        value: String do email a validar.

    Returns:
        True se válido, False caso contrário.
    """
    if not value:
        return False
    try:
        _validate_email_lib(value, check_deliverability=False)
    except EmailNotValidError:
        return False
    return True

def validate_phone_number(value: str | None) -> bool:
    """ Valida se o telefone segue o padrão E.164 básico (+DDI + número, 10-15 dígitos).

    Args:
        value: String do telefone a validar.

    Returns:
        True se válido, False caso contrário.
    """
    if not value:
        return False
    return re.fullmatch(r"^\+\d{10,15}$", value) is not None
