"""Utilitários públicos da feature de coletores.

Mantém tipos compartilhados de despacho contínuo e evita importações diretas de
módulos utilitários internos.
"""

from market_alert.collectors.utils.continuous_dispatch import CollectDispatchDecision

__all__ = ["CollectDispatchDecision"]
