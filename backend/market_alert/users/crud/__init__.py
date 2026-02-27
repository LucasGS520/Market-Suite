""" Composição dos módulos de persistência do domínio de usuários.
 
Mantém a importação dos repositórios concentrada neste módulo para
reduzir acoplamento com a estrutura interna da pasta `crud`.
"""

from market_alert.users.crud import crud_account, crud_identity

__all__ = ["crud_account", "crud_identity"]
