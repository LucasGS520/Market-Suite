""" Contratos públicos do domínio de coletores.

Este módulo expõe apenas interfaces/facades estáveis para consumidores externos,
evitar importações diretas de submódulos reduz acoplamento com detalhes internos.
"""

from market_alert.collectors.domain.collection_callbacks import CollectionCallbacks
from market_alert.collectors.domain.collection_queue import CollectionQueue
from market_alert.collectors.domain.collection_reconciliation import reconcile_collection_queue
from market_alert.collectors.domain.collection_triggers import trigger_comparison_if_needed

__all__ = [
    "CollectionCallbacks",
    "CollectionQueue",
    "reconcile_collection_queue",
    "trigger_comparison_if_needed",
]
