""" Regras e utilitários de domínio para usuários 

Este módulo centraliza regras e constantes reutilizadas pelos serviços,
sem expor detalhes internos de implementação dos arquivos da pasta.
"""

from market_alert.users.domain.account_domain import normalize_email, normalize_phone
from market_alert.users.domain.identity_domain import VERIFICATION_CHANNEL_TO_KIND
from market_alert.users.domain.settings_domain import DEFAULT_NOTIFICATION_CHANNELS

__all__ = [
    "normalize_email",
    "normalize_phone",
    "VERIFICATION_CHANNEL_TO_KIND",
    "DEFAULT_NOTIFICATION_CHANNELS",
]
