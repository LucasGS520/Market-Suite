""" Enumerações específicas para regras de comparação de preços """

from enum import Enum


class CompetitivenessStatus(str, Enum):
    """ Define estados padronizados de competitividade utilizados nos dashboards """
    COMPETITIVE = "competitivo"
    NON_COMPETITIVE = "nao_competitivo"
    ATTENTION = "atencao"
    URGENT = "urgente"

__all__ = ["CompetitivenessStatus"]
