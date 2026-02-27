""" Camada de persistência da feature de notificações. 

Este módulo expõe apenas operações CRUD consideradas estáveis para uso
externo, evitando acoplamento direto ao arquivo de implementação.
"""

from market_alert.notifications.crud.crud_notifications import (
    acquire_notification_for_processing,
    add_notification_attempt,
    create_alert_rule,
    create_event_log,
    create_notification,
    get_notification_settings,
    get_pending_notifications,
    list_notifications_for_user,
    list_user_notification_preferences,
    mark_notification_dead_letter,
    mark_notification_failed,
    mark_notification_sent,
    update_notification_settings,
    upsert_user_notification_preference,
)

__all__ = [
    "create_event_log",
    "create_alert_rule",
    "create_notification",
    "get_pending_notifications",
    "acquire_notification_for_processing",
    "mark_notification_sent",
    "mark_notification_failed",
    "mark_notification_dead_letter",
    "add_notification_attempt",
    "upsert_user_notification_preference",
    "list_notifications_for_user",
    "list_user_notification_preferences",
    "get_notification_settings",
    "update_notification_settings",
]
