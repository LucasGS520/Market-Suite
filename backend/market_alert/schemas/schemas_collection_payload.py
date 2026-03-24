"""Contrato explícito de payload para coletas de produtos.

Re-exporta CollectionPayload e validate_payload de shared para manter
backward compatibility com todos os importadores existentes.

Fonte canônica: shared.schemas.shared_schemas_orchestrator
"""
from shared.schemas.shared_schemas_orchestrator import (
    CollectionPayload,
    validate_payload,
)

__all__ = [
    "CollectionPayload",
    "validate_payload",
]
