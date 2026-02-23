"""Pacote de orquestração de coletas.

Expõe as interfaces públicas do orquestrador. Todo módulo externo que precise
enfileirar coletas, acessar a fila Redis ou definir callbacks deve importar
daqui — nunca de submódulos internos diretamente.

Componentes disponíveis:

    CollectionEnqueuer        — porta de entrada única para enfileirar coletas.
    CollectionQueue           — abstração de domínio sobre PriorityQueueService.
    RetryPolicy               — política centralizada de retry (lock e scrape).
    CollectionCallbacks       — callbacks padronizados de sucesso e erro.
    trigger_comparison_if_needed — desacopla disparo de comparação da coleta.
    reconcile_collection_queue   — reconcilia fila Redis com estado do banco.

Compatibilidade (funções e builders do módulo anterior):

    build_monitored_payload       — constrói CollectionPayload para monitorados.
    build_competitor_payload      — constrói CollectionPayload para concorrentes.
    enqueue_collect               — enfileira payload (CollectionPayload ou dict).
    enqueue_monitored_collection  — abstrai enqueue de monitorado com pausa check.
    enqueue_competitor_collection — abstrai enqueue de concorrente.
    enqueue_competitors_for_monitored — enfileira concorrentes com batching/jitter.
"""

from market_alert.orchestrator.collection_callbacks import CollectionCallbacks
from market_alert.orchestrator.collection_enqueuer import CollectionEnqueuer
from market_alert.orchestrator.collection_queue import CollectionQueue
from market_alert.orchestrator.collection_reconciliation import reconcile_collection_queue
from market_alert.orchestrator.collection_triggers import trigger_comparison_if_needed
from market_alert.orchestrator.collector_service_orchestrator import (
    build_competitor_payload,
    build_monitored_payload,
    enqueue_collect,
    enqueue_competitor_collection,
    enqueue_competitors_for_monitored,
    enqueue_monitored_collection,
)
from market_alert.orchestrator.retry_policy import RetryPolicy

__all__ = [
    #Novos componentes da refatoração
    "CollectionCallbacks",
    "CollectionEnqueuer",
    "CollectionQueue",
    "RetryPolicy",
    "reconcile_collection_queue",
    "trigger_comparison_if_needed",
    #Funções de compatibilidade (builders e helpers de enqueue)
    "build_competitor_payload",
    "build_monitored_payload",
    "enqueue_collect",
    "enqueue_competitor_collection",
    "enqueue_competitors_for_monitored",
    "enqueue_monitored_collection",
]
