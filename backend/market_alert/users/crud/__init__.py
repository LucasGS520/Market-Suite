""" Composição dos módulos de persistência do domínio de usuários. """

from market_alert.users.crud import crud_account, crud_identity

__all__ = ["crud_account", "crud_identity"]
