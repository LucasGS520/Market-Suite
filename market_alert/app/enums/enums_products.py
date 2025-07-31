""" Enumerações relacionadas a produtos monitorados e seu status """

from enum import Enum


class MonitoringType(str, Enum):
    """ Define como o produto é monitorado """
    api = "api" #Dados obtidos via API externa
    scraping = "scraping" #Dados obtidos por scraping

class MonitoredStatus(str, Enum):
    """ Estado da configuração de monitoramento """
    active = "active" #Monitoramento ativo
    inactive = "inactive" #Monitoramento inativo
    pending = "pending" #Aguardando coleta inicial
    failed = "failed" #Se falhar scraping

class ProductStatus(str, Enum):
    """ Estado atual do anúncio no marketplace """
    available = "available" #Produto disponível
    unavailable = "unavailable" #Produto indisponível
    removed = "removed" #Anúncio removido
