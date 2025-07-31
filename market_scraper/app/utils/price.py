""" Conversão e manipulação de valores monetários """

from decimal import Decimal, InvalidOperation
from fastapi import HTTPException, status


def parse_price_str(raw: str, url: str) -> Decimal:
    """ Converte string de preço no formato 'R$ 1.234,56' em Decimal ('1234.56')

    - raw: string retornada pelo parser (ex.: "R$ 1.234,56")
    - url: URL analisada (para compor mensagem de erro)

    Levanta HTTPException 400 se houver falha
    """
    if not raw or not raw.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Preço não encontrado em na página {url}"
        )

    #Fromata o preço em versão brasileira
    num = raw.replace("R$", "").strip().replace(".", "").replace(",", ".")
    try:
        return Decimal(num)
    except (InvalidOperation, AttributeError):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Preço inválido em {url}: {raw}"
        )

def parse_optional_price_str(raw: str | None, url: str) -> Decimal | None:
    """ Mesma logica do parse_price_str, mas retorna None se raw estiver vazio """
    if not raw or not raw.strip():
        return None
    return parse_price_str(raw, url)
