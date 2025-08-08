""" Enumerações de resultados ao lidar com bloqueios de scraping """

from enum import Enum


class BlockResult(str, Enum):
    """ Resultados possíveis ao detectar bloqueios """
    OK = "ok" #Acesso liberado
    CAPTCHA = "captcha" #Foi solicitado CAPTCHA
    HTTP_429 = "http_429" #Muitas requisições (429)
    HTTP_403 = "http_403" #Acesso negado (403)
    UNKNOWN = "unknown" #Tipo de bloqueio não identificado
