"""Facade de roteadores HTTP da feature de notificações."""

from market_alert.notifications.routes.routes_notifications import (
    router as notifications_router,
)

__all__ = ["notifications_router"]
