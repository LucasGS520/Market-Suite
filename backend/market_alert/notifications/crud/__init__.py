""" Camada de persistência da feature de notificações. 

Centraliza o módulo CRUD estável para evitar dependência direta de caminhos
internos e facilitar futuras reorganizações de código.
"""

from market_alert.notifications.crud import crud_notifications

__all__ = ["crud_notifications"]
