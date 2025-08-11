""" Utilitários específicos do módulo MarketAlert

Este pacote reexporta utilitários compartilhados e expõe
funções adicionais empregadas pelo serviço de alertas
"""

from shared.utils import *
import sys as _sys
import shared.utils.rate_limiter as rate_limiter
import shared.utils.circuit_breaker as circuit_breaker
import shared.utils.redis_client as redis_client
import shared.utils.ml_url as ml_url

#Exporta módulos utilitários compartilhados sob o namespace ``market_alert.utils``
_sys.modules.setdefault("market_alert.utils.rate_limiter", rate_limiter)
_sys.modules.setdefault("market_alert.utils.circuit_breaker", circuit_breaker)
_sys.modules.setdefault("market_alert.utils.redis_client", redis_client)
_sys.modules.setdefault("market_alert.utils.ml_url", ml_url)
