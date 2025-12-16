""" Enumerações específicas para regras de comparação de preços """

from enum import Enum


class CompetitivenessStatus(str, Enum):
    """ Define estados padronizados de competitividade utilizados nos dashboards """
    COMPETITIVE = "competitivo"
    # Mantido o membro para compatibilidade de código, mas seu valor
    # agora é representado como 'atencao' para simplificar as faixas.
    NON_COMPETITIVE = "atencao"
    ATTENTION = "atencao"
    URGENT = "urgente"

__all__ = ["CompetitivenessStatus"]
