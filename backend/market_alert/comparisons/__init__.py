""" Facade do pacote de comparações sem import eager.

Evita carregar submódulos no import do pacote para prevenir dependências
circulares durante o bootstrap da aplicação.
"""

__all__ = ["crud", "domain", "routes", "services", "tasks", "utils"]
