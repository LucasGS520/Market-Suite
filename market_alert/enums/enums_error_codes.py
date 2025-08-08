""" Códigos de erro utilizados durante o processo de scraping """

from enum import Enum


class ScrapingErrorType(str, Enum):
    """ Tipos de erro possíveis durante o scraping de produtos """

    http_error = "http_error" #Falhas HTTP 4xx ou 5xx
    missing_data = "missing_data" #Dados essenciais ausentes
    timeout = "timeout" #Tempo de resposta excedida
    parsing_error = "parsing_error" #Erro ao analisar a página
