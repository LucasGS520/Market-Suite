"""Re-exporta TemporalOrchestrationClient de shared para compatibilidade.

Fonte canônica: shared.clients.orchestrator_client
"""
from shared.clients.orchestrator_client import (
    TemporalOrchestrationClient,
    get_temporal_client,
)

__all__ = ["TemporalOrchestrationClient", "get_temporal_client"]
