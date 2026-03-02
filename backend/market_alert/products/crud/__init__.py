""" Acesso a dados de monitorados e concorrentes.

A composição explícita garante imports consistentes entre serviços internos e
testes que dependem dos contratos de pacote.
"""

from market_alert.products.crud import crud_competitor, crud_monitored, crud_price_history

__all__ = ["crud_competitor", "crud_monitored", "crud_price_history"]
