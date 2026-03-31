""" Cliente Temporal — ponto único de integração com o orquestrador.

É o único módulo que os services de domínio devem importar para interagir
com o Temporal. Encapsula toda a complexidade do SDK e implementa fallback
não-bloqueante: falhas de conexão são logadas e retornam None sem propagar.

Dependências de runtime do market_orchestrator (WorkflowInput, signals, etc.)
são importadas de forma lazy dentro dos métodos de facade, evitando dependência
circular em nível de módulo.
"""
from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any

import structlog
from temporalio.client import Client
from temporalio.common import WorkflowIDReusePolicy
from temporalio.service import RPCError

from shared.exceptions import TemporalConnectionError
from shared.utils.async_utils import run_sync_coro

if TYPE_CHECKING:
    from market_orchestrator.schemas.schemas_snapshot import WorkflowSnapshot
    from shared.schemas.shared_schemas_orchestrator import WorkflowInput


logger = structlog.get_logger("orchestrator.client")

def _config():
    """ Lazy accessor para OrchestratorSettings — evita import no nível de módulo.

    O import em nível de módulo acionaria Path.expanduser() durante carregamento,
    proibido pelo sandbox determinístico do Temporal SDK.
    """
    from market_orchestrator.core.config_orchestrator import settings
    return settings

# Política de reutilização de ID: permite novo workflow se o anterior terminou/falhou
_WORKFLOW_ID_REUSE = WorkflowIDReusePolicy.ALLOW_DUPLICATE_FAILED_ONLY

def _workflow_id(monitored_id: str) -> str:
    return f"monitored:{monitored_id}"

class TemporalOrchestrationClient:
    """ Adaptador assíncrono entre o domínio e o Temporal SDK.

    Uso típico (código síncrono de services):
        client = TemporalOrchestrationClient()
        client.signal_with_start_sync(input)
    """

    def __init__(self) -> None:
        self._client: Client | None = None

    # ------------------------------------------------------------------
    # Conexão lazy
    # ------------------------------------------------------------------

    async def _get_client(self) -> Client:
        if self._client is not None:
            return self._client

        delays = [1, 2, 4, 8, 16, 30, 30]
        last_exc: Exception | None = None
        for attempt, delay in enumerate(delays, 1):
            try:
                self._client = await Client.connect(
                    _config().temporal_target,
                    namespace=_config().TEMPORAL_NAMESPACE,
                )
                if attempt > 1:
                    logger.info(
                        "temporal_client_connected_after_retry",
                        attempt=attempt,
                        max_attempts=len(delays),
                        target=_config().temporal_target,
                    )
                return self._client
            except Exception as exc:
                last_exc = exc
                self._client = None
                has_next = attempt < len(delays)
                logger.info(
                    "temporal_client_connect_attempt_failed",
                    attempt=attempt,
                    max_attempts=len(delays),
                    target=_config().temporal_target,
                    next_retry_in_seconds=delay if has_next else None,
                    error=str(exc),
                )
                if has_next:
                    await asyncio.sleep(delay)

        raise TemporalConnectionError(
            f"Temporal Server inacessível após {len(delays)} tentativas",
            attempts=len(delays),
            target=_config().temporal_target,
        ) from last_exc

    # ------------------------------------------------------------------
    # Métodos assíncronos
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
        logger.info(
            "temporal_signal_with_start_attempt",
            monitored_id=input.monitored_id,
            signal_name=signal_name or "start",
            target=_config().temporal_target,
        )
        try:
            client = await self._get_client()
            handle = await client.start_workflow(
                "MonitoredProductWorkflow",
                input,
                id=_workflow_id(input.monitored_id),
                task_queue=_config().TEMPORAL_TASK_QUEUE,
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
        """ Envia signal a um workflow existente.

        WorkflowNotFound é logado como warning — reconciliador resolverá.
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
        """ Consulta get_state de um workflow por monitored_id."""
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
    # Wrappers síncronos (para FastAPI/Celery síncronos)
    # ------------------------------------------------------------------

    def _run_async(self, coro: Any, *, timeout: int = 30) -> Any:
        """ Executa coroutine reutilizando loop existente ou criando um novo."""
        import concurrent.futures
        try:
            return run_sync_coro(coro, timeout=timeout)
        except concurrent.futures.TimeoutError:
            logger.error("temporal_client_run_async_timeout", timeout_seconds=timeout)
            return None
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
        success = bool(result)
        if success:
            logger.info(
                "temporal_workflow_signal_succeeded",
                workflow_id=_workflow_id(str(input.monitored_id)),
                signal_name=signal_name or "start",
            )
        return success

    def signal_sync(
        self,
        signal_name: str,
        monitored_id: str,
        payload: Any = None,
    ) -> bool:
        result = self._run_async(self.signal(signal_name, monitored_id, payload))
        success = bool(result)
        if success:
            logger.info(
                "temporal_workflow_signal_succeeded",
                workflow_id=_workflow_id(monitored_id),
                signal_name=signal_name,
            )
        return success

    def query_sync(self, monitored_id: str) -> WorkflowSnapshot | None:
        return self._run_async(self.query(monitored_id))

    async def probe_connectivity(self) -> bool:
        """ Verifica conectividade com o Temporal Server (sem retry com sleep)."""
        if self._client is not None:
            return True
        try:
            self._client = await Client.connect(
                _config().temporal_target,
                namespace=_config().TEMPORAL_NAMESPACE,
            )
            return True
        except Exception as exc:
            logger.warning("temporal_connectivity_probe_failed", error=str(exc))
            return False

    def probe_connectivity_sync(self, *, timeout: int = 30) -> bool:
        """ Versão síncrona de probe_connectivity para endpoints FastAPI síncronos."""
        result = self._run_async(self.probe_connectivity(), timeout=timeout)
        return bool(result)

    # ------------------------------------------------------------------
    # Facade de domínio — oculta signal names, payload types e WorkflowInput
    # Importadores externos devem usar APENAS estes métodos
    # ------------------------------------------------------------------

    def start_monitoring(
        self,
        monitored_id: Any,
        user_id: Any,
        interval_seconds: int = 3600,
    ) -> bool:
        """ Inicia (ou idempotentemente retoma) o workflow de monitoramento."""
        from shared.schemas.shared_schemas_orchestrator import CollectionPolicy, WorkflowInput
        return self.signal_with_start_sync(WorkflowInput(
            monitored_id=str(monitored_id),
            user_id=str(user_id),
            policy=CollectionPolicy(interval_seconds=interval_seconds),
        ))

    def pause_monitoring(self, monitored_id: Any) -> bool:
        """ Envia signal de pausa para o workflow do monitorado."""
        return self.signal_sync("pause", str(monitored_id))

    def resume_monitoring(
        self,
        monitored_id: Any,
        *,
        immediate_collect: bool = True,
    ) -> bool:
        """ Envia signal de retomada, com opção de coleta imediata."""
        from shared.schemas.shared_schemas_orchestrator import ResumeSignalPayload
        return self.signal_sync(
            "resume",
            str(monitored_id),
            ResumeSignalPayload(immediate_collect=immediate_collect),
        )

    def delete_monitoring(self, monitored_id: Any) -> bool:
        """ Envia signal de deleção para encerrar o workflow do monitorado."""
        return self.signal_sync("delete", str(monitored_id))

    def notify_competitor_changed(
        self,
        monitored_id: Any,
        *,
        event: str,
        competitor_id: Any,
    ) -> bool:
        """ Notifica o workflow que um concorrente foi adicionado ou removido."""
        from shared.schemas.shared_schemas_orchestrator import CompetitorChangedPayload
        return self.signal_sync(
            "competitor_changed",
            str(monitored_id),
            CompetitorChangedPayload(event=event, competitor_id=str(competitor_id)),
        )


# Instância singleton lazy — inicializada na primeira chamada
_client_instance: TemporalOrchestrationClient | None = None

def get_temporal_client() -> TemporalOrchestrationClient:
    """ Retorna instância singleton de TemporalOrchestrationClient."""
    global _client_instance
    if _client_instance is None:
        _client_instance = TemporalOrchestrationClient()
    return _client_instance

def get_temporal_connection_info() -> dict:
    """ Retorna namespace e task_queue configurados para o Temporal.

    Evita que consumidores (ex: health route) importem diretamente
    market_orchestrator.core.config_orchestrator.
    """
    cfg = _config()
    return {
        "namespace": cfg.TEMPORAL_NAMESPACE,
        "task_queue": cfg.TEMPORAL_TASK_QUEUE,
    }
