""" Cliente adaptador Temporal para o domínio market_alert.

É o único ponto que os services de domínio devem importar para interagir
com o Temporal. Encapsula toda a complexidade do SDK e implementa
fallback não-bloqueante (P6): falhas de conexão são logadas e retornam
None sem propagar para o chamador.
"""
from __future__ import annotations

import asyncio
from typing import Any

import structlog
from temporalio.client import Client
from temporalio.service import RPCError

from market_orchestrator.core.config_orchestrator import settings
from market_orchestrator.enums.enums_workflow import WorkflowState
from market_orchestrator.schemas.schemas_signals import (
    CompetitorChangedPayload,
    ResumeSignalPayload,
    UpdatePolicySignalPayload,
)
from market_orchestrator.schemas.schemas_snapshot import WorkflowSnapshot
from market_orchestrator.schemas.schemas_workflow import WorkflowInput
from market_orchestrator.worker import TASK_QUEUE
from shared.exceptions import TemporalUnavailableError


logger = structlog.get_logger("orchestrator.client")

# Política de reutilização de ID: permite criar novo workflow se o anterior completou/falhou
_WORKFLOW_ID_REUSE = "ALLOW_DUPLICATE_FAILED_ONLY"

def _workflow_id(monitored_id: str) -> str:
    return f"monitored:{monitored_id}"

class TemporalOrchestrationClient:
    """ Adaptador assíncrono entre o domínio market_alert e o Temporal SDK.

    Uso típico (em código síncrono dos services):
        client = TemporalOrchestrationClient()
        client.signal_with_start_sync(input, "resume", payload)
    """

    def __init__(self) -> None:
        self._client: Client | None = None

    # ------------------------------------------------------------------
    # Conexão lazy
    # ------------------------------------------------------------------

    async def _get_client(self) -> Client:
        if self._client is None:
            self._client = await Client.connect(
                settings.temporal_target,
                namespace=settings.TEMPORAL_NAMESPACE,
            )
        return self._client

    # ------------------------------------------------------------------
    # Métodos assíncronos (para uso em contexto async)
    # ------------------------------------------------------------------

    async def signal_with_start(
        self,
        input: WorkflowInput,
        signal_name: str | None = None,
        signal_arg: Any = None,
    ) -> bool:
        """ Cria ou sinaliza o workflow de forma idempotente.

        Retorna True em sucesso, False em falha não-bloqueante.
        """
        try:
            client = await self._get_client()
            handle = await client.start_workflow(
                "MonitoredProductWorkflow",
                input,
                id=_workflow_id(input.monitored_id),
                task_queue=TASK_QUEUE,
                id_reuse_policy=_WORKFLOW_ID_REUSE,
            )
            if signal_name and signal_arg is not None:
                await handle.signal(signal_name, signal_arg)
            elif signal_name:
                await handle.signal(signal_name)
            return True

        except Exception as exc:
            logger.error(
                "temporal_client_signal_with_start_error",
                monitored_id=input.monitored_id,
                error=str(exc),
            )
            return False

    async def signal(
        self,
        signal_name: str,
        monitored_id: str,
        payload: Any = None,
    ) -> bool:
        """ Envia signal a um workflow existente por monitored_id.

        Retorna True em sucesso. WorkflowNotFound é logado como warning
        (não fatal — reconciliador resolverá na próxima passagem).
        """
        try:
            client = await self._get_client()
            handle = client.get_workflow_handle(_workflow_id(monitored_id))
            if payload is not None:
                await handle.signal(signal_name, payload)
            else:
                await handle.signal(signal_name)
            return True

        except RPCError as exc:
            if "workflow not found" in str(exc).lower():
                logger.warning(
                    "temporal_client_workflow_not_found",
                    signal=signal_name,
                    monitored_id=monitored_id,
                )
            else:
                logger.error(
                    "temporal_client_signal_error",
                    signal=signal_name,
                    monitored_id=monitored_id,
                    error=str(exc),
                )
            return False

        except Exception as exc:
            logger.error(
                "temporal_client_unreachable",
                signal=signal_name,
                monitored_id=monitored_id,
                error=str(exc),
            )
            return False

    async def query(self, monitored_id: str) -> WorkflowSnapshot | None:
        """ Consulta get_state de um workflow por monitored_id.

        Retorna WorkflowSnapshot ou None se não encontrado / indisponível.
        """
        try:
            client = await self._get_client()
            handle = client.get_workflow_handle(_workflow_id(monitored_id))
            snapshot: WorkflowSnapshot = await handle.query("get_state")
            return snapshot

        except RPCError as exc:
            if "workflow not found" in str(exc).lower():
                return None
            logger.error(
                "temporal_client_query_error",
                monitored_id=monitored_id,
                error=str(exc),
            )
            return None

        except Exception as exc:
            logger.error(
                "temporal_client_unreachable",
                monitored_id=monitored_id,
                error=str(exc),
            )
            return None

    # ------------------------------------------------------------------
    # Wrappers síncronos (para chamada a partir de código síncrono FastAPI/Celery)
    # ------------------------------------------------------------------

    def _run_async(self, coro: Any) -> Any:
        """ Executa coroutine em event loop existente ou cria um novo """
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                # Contexto assíncrono (FastAPI): schedule e aguarda via thread
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                    future = pool.submit(asyncio.run, coro)
                    return future.result(timeout=10)
            else:
                return loop.run_until_complete(coro)
        except Exception as exc:
            logger.error("temporal_client_unreachable", error=str(exc))
            return None

    def signal_with_start_sync(
        self,
        input: WorkflowInput,
        signal_name: str | None = None,
        signal_arg: Any = None,
    ) -> bool:
        result = self._run_async(self.signal_with_start(input, signal_name, signal_arg))
        return bool(result)

    def signal_sync(
        self,
        signal_name: str,
        monitored_id: str,
        payload: Any = None,
    ) -> bool:
        result = self._run_async(self.signal(signal_name, monitored_id, payload))
        return bool(result)

    def query_sync(self, monitored_id: str) -> WorkflowSnapshot | None:
        return self._run_async(self.query(monitored_id))

    async def probe_connectivity(self) -> bool:
        """ Verifica conectividade com o Temporal Server.

        Retorna True se a conexão foi estabelecida, False caso contrário.
        Não lança exceções — usado pelo health check.
        """
        try:
            await self._get_client()
            return True
        except Exception as exc:
            logger.warning("temporal_connectivity_probe_failed", error=str(exc))
            return False

    def probe_connectivity_sync(self) -> bool:
        """ Versão síncrona de probe_connectivity para uso em endpoints FastAPI síncronos."""
        result = self._run_async(self.probe_connectivity())
        return bool(result)


#Instância singleton lazy — inicializada na primeira chamada
_client_instance: TemporalOrchestrationClient | None = None

def get_temporal_client() -> TemporalOrchestrationClient:
    """ Retorna instância singleton de TemporalOrchestrationClient."""
    global _client_instance
    if _client_instance is None:
        _client_instance = TemporalOrchestrationClient()
    return _client_instance
