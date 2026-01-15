""" Métricas relacionadas às atualizações de configurações do usuário """

from prometheus_client import Counter

SETTINGS_PROFILE_UPDATES_TOTAL = Counter(
    "settings_profile_updates_total",
    "Total de atualizações de perfil feitas pela tela de configurações",
    ["result"],
)
SETTINGS_NOTIFICATION_UPDATES_TOTAL = Counter(
    "settings_notification_updates_total",
    "Total de atualizações de canais de notificação",
    ["result"],
)

__all__ = [
    "SETTINGS_PROFILE_UPDATES_TOTAL",
    "SETTINGS_NOTIFICATION_UPDATES_TOTAL",
]
