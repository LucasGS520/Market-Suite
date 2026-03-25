""" Workflow Temporal de monitoramento contínuo por produto.

Regras obrigatórias (determinismo):
- ZERO I/O aqui. ZERO imports de infra, banco ou HTTP.
- Toda geração de tempo usa workflow.now(). Todo UUID usa workflow.uuid4().
- Toda operação externa é delegada a uma Activity.
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone

import structlog
from temporalio import workflow
from temporalio.common import RetryPolicy
from temporalio.exceptions import ActivityError

with workflow.unsafe.imports_passed_through():
    from market_orchestrator.core.config_orchestrator import settings
    from market_orchestrator.enums.enums_workflow import WorkflowState
    from market_orchestrator.schemas.schemas_policy import CollectionPolicy, PolicyActivityResponse
    from market_orchestrator.schemas.schemas_signals import (
        ResumeSignalPayload,
        UpdatePolicySignalPayload,
        CompetitorChangedPayload,
    )
    from market_orchestrator.schemas.schemas_snapshot import WorkflowSnapshot
    from market_orchestrator.schemas.schemas_workflow import WorkflowInput
    from shared.schemas.shared_schemas_orchestrator import DispatchActivityOutput, QueryStatusOutput
    

logger = structlog.get_logger("orchestrator.workflow")

#Limites para Continue-As-New
_HISTORY_LENGTH_LIMIT = settings.WORKFLOW_HISTORY_LENGTH_LIMIT
_SIGNAL_COUNT_LIMIT = settings.WORKFLOW_SIGNAL_COUNT_LIMIT

#Timeout máximo de espera por resultado de coleta (polling)
_COLLECTION_RESULT_TIMEOUT_SECONDS = settings.COLLECTION_RESULT_TIMEOUT_SECONDS
_COLLECTION_POLL_INTERVAL_SECONDS = settings.COLLECTION_POLL_INTERVAL_SECONDS

#Retry policy padrão para activities
_DEFAULT_RETRY = RetryPolicy(
    maximum_attempts=settings.RETRY_MAX_ATTEMPTS,
    initial_interval=timedelta(seconds=settings.RETRY_INITIAL_INTERVAL_SECONDS),
    maximum_interval=timedelta(seconds=settings.RETRY_MAX_INTERVAL_SECONDS),
    backoff_coefficient=settings.RETRY_BACKOFF_COEFFICIENT,
)

#Activity timeouts
_DISPATCH_TIMEOUT = timedelta(seconds=settings.ACTIVITY_DISPATCH_TIMEOUT_SECONDS)
_QUERY_STATUS_TIMEOUT = timedelta(seconds=settings.ACTIVITY_QUERY_STATUS_TIMEOUT_SECONDS)
_PERSIST_SNAPSHOT_TIMEOUT = timedelta(seconds=settings.ACTIVITY_PERSIST_SNAPSHOT_TIMEOUT_SECONDS)
_CLEANUP_TIMEOUT = timedelta(seconds=settings.ACTIVITY_CLEANUP_TIMEOUT_SECONDS)
_FETCH_POLICY_TIMEOUT = timedelta(seconds=settings.ACTIVITY_FETCH_POLICY_TIMEOUT_SECONDS)

@workflow.defn(name="MonitoredProductWorkflow")
class MonitoredProductWorkflow:
    """ Workflow durável de orquestração contínua por monitorado.

    workflow_id estável: f"monitored:{monitored_id}"
    """

    def __init__(self) -> None:
        self._state: WorkflowState = WorkflowState.Active
        self._policy: CollectionPolicy = CollectionPolicy()
        self._monitored_id: str = ""
        self._user_id: str = ""
        self._attempt_count: int = 0
        self._signal_count: int = 0
        self._last_run_at: datetime | None = None
        self._next_run_at: datetime | None = None
        self._last_error: str | None = None

        #Flags de controle de signals
        self._pause_requested: bool = False
        self._resume_payload: ResumeSignalPayload | None = None
        self._delete_requested: bool = False
        self._competitor_changed: bool = False
        self._policy_update: CollectionPolicy | None = None

    # ------------------------------------------------------------------
    # Entry point
    # ------------------------------------------------------------------

    @workflow.run
    async def run(self, input: WorkflowInput) -> None:
        self._monitored_id = input.monitored_id
        self._user_id = input.user_id
        self._policy = input.policy

        #Restaura estado após Continue-As-New
        if resume_state := input.bootstrap_flags.get("resume_state"):
            try:
                self._state = WorkflowState(resume_state)
            except ValueError:
                self._state = WorkflowState.WaitingTimer
        else:
            self._state = WorkflowState.WaitingTimer

        await self._run_loop()

    # ------------------------------------------------------------------
    # Loop principal
    # ------------------------------------------------------------------

    async def _run_loop(self) -> None:
        while True:
            #Continue-As-New preventivo
            info = workflow.info()
            if (
                info.get_current_history_length() >= _HISTORY_LENGTH_LIMIT
                or self._signal_count >= _SIGNAL_COUNT_LIMIT
            ):
                await self._continue_as_new()
                return

            if self._state == WorkflowState.WaitingTimer:
                await self._handle_waiting_timer()

            elif self._state == WorkflowState.Dispatching:
                await self._handle_dispatching()

            elif self._state == WorkflowState.WaitingResult:
                await self._handle_waiting_result()

            elif self._state == WorkflowState.Backoff:
                await self._handle_backoff()

            elif self._state == WorkflowState.Paused:
                await self._handle_paused()

            elif self._state == WorkflowState.FailedTerminal:
                await self._handle_failed_terminal()
                return

            elif self._state == WorkflowState.CompletedDeleted:
                return

    # ------------------------------------------------------------------
    # Estados
    # ------------------------------------------------------------------

    async def _handle_waiting_timer(self) -> None:
        """ Aguarda até next_check_at ou até receber um signal que preempte."""
        policy_data = await workflow.execute_activity(
            "fetch_monitored_policy",
            args=[self._monitored_id],
            start_to_close_timeout=_FETCH_POLICY_TIMEOUT,
            retry_policy=_DEFAULT_RETRY,
        )
        resp = PolicyActivityResponse.from_dict(policy_data)

        #Se pausado externamente, transicionar
        if resp.paused:
            self._state = WorkflowState.Paused
            return

        #Atualiza policy com valores frescos (preserva backoff settings do signal update_policy)
        self._policy = CollectionPolicy(
            interval_seconds=resp.interval_seconds,
            backoff_max_attempts=self._policy.backoff_max_attempts,
            backoff_base_seconds=self._policy.backoff_base_seconds,
            stability_score=resp.stability_score,
            scheduling_reason=resp.scheduling_reason,
        )

        #Aplica atualização de política pendente (pode sobrescrever backoff settings)
        if self._policy_update is not None:
            self._policy = self._policy_update
            self._policy_update = None

        #Calcula delta até próxima coleta
        if resp.next_check_at:
            next_check_at = datetime.fromisoformat(resp.next_check_at)
            delta = (next_check_at - workflow.now()).total_seconds()
            sleep_seconds = max(delta, 0)
        else:
            sleep_seconds = float(self._policy.interval_seconds)

        self._next_run_at = workflow.now() + timedelta(seconds=sleep_seconds)

        await self._persist_snapshot()

        #Espera com possibilidade de preempção por signal
        preempted = await self._sleep_preemptible(sleep_seconds)
        if not preempted:
            self._state = WorkflowState.Dispatching

    async def _handle_dispatching(self) -> None:
        """ Enfileira coleta e transiciona para WaitingResult."""
        correlation_id = str(workflow.uuid4())
        trace_id = str(workflow.uuid4())

        try:
            _result: DispatchActivityOutput = await workflow.execute_activity(
                "dispatch_collection",
                args=[self._monitored_id, self._user_id, correlation_id, trace_id, False],
                start_to_close_timeout=_DISPATCH_TIMEOUT,
                retry_policy=_DEFAULT_RETRY,
            )
            self._state = WorkflowState.WaitingResult
            self._last_run_at = workflow.now()
            self._last_error = None
            #correlation_id salvo internamente para polling
            self._current_correlation_id = correlation_id

        except ActivityError as exc:
            self._last_error = str(exc)
            self._state = WorkflowState.Backoff

    async def _handle_waiting_result(self) -> None:
        """ Polling até coleta concluída ou timeout."""
        correlation_id = getattr(self, "_current_correlation_id", "")
        deadline = workflow.now() + timedelta(seconds=_COLLECTION_RESULT_TIMEOUT_SECONDS)

        while workflow.now() < deadline:
            #Verifica preempção por signals antes de cada poll
            if self._delete_requested:
                await self._do_delete()
                return
            if self._pause_requested:
                self._pause_requested = False
                self._state = WorkflowState.Paused
                return

            result: QueryStatusOutput = await workflow.execute_activity(
                "query_collection_status",
                args=[self._monitored_id, correlation_id],
                start_to_close_timeout=_QUERY_STATUS_TIMEOUT,
                retry_policy=_DEFAULT_RETRY,
            )

            if result.completed:
                self._attempt_count = 0
                self._state = WorkflowState.WaitingTimer
                await self._persist_snapshot()
                return

            if result.last_error:
                self._last_error = result.last_error

            await workflow.sleep(timedelta(seconds=_COLLECTION_POLL_INTERVAL_SECONDS))

        #Timeout — vai para backoff
        self._last_error = "collection_result_timeout"
        self._state = WorkflowState.Backoff

    async def _handle_backoff(self) -> None:
        """ Backoff exponencial com jitter. Após max_attempts, FailedTerminal."""
        self._attempt_count += 1
        if self._attempt_count >= self._policy.backoff_max_attempts:
            self._state = WorkflowState.FailedTerminal
            return

        sleep_seconds = min(
            self._policy.backoff_base_seconds * (2 ** (self._attempt_count - 1)),
            3600,
        )
        #Jitter: ±20% (determinístico via workflow.uuid4 não usado aqui — sleep simples)
        await workflow.sleep(timedelta(seconds=sleep_seconds))
        self._state = WorkflowState.Dispatching

    async def _handle_paused(self) -> None:
        """ Aguarda signal de resume."""
        await self._persist_snapshot()
        await workflow.wait_condition(
            lambda: self._resume_payload is not None or self._delete_requested
        )

        if self._delete_requested:
            await self._do_delete()
            return

        payload = self._resume_payload
        self._resume_payload = None
        self._attempt_count = 0

        if payload and payload.immediate_collect:
            self._state = WorkflowState.Dispatching
        else:
            self._state = WorkflowState.WaitingTimer

    async def _handle_failed_terminal(self) -> None:
        """ Estado terminal de falha — persiste snapshot e encerra."""
        self._state = WorkflowState.FailedTerminal
        await self._persist_snapshot()
        #Workflow encerra; pode ser reiniciado manualmente via reconciliador

    # ------------------------------------------------------------------
    # Signals
    # ------------------------------------------------------------------

    @workflow.signal(name="pause")
    async def signal_pause(self) -> None:
        self._signal_count += 1
        self._pause_requested = True
        if self._state not in (WorkflowState.Paused, WorkflowState.CompletedDeleted):
            self._state = WorkflowState.Paused

    @workflow.signal(name="resume")
    async def signal_resume(self, payload: ResumeSignalPayload) -> None:
        self._signal_count += 1
        self._resume_payload = payload
        self._pause_requested = False

    @workflow.signal(name="delete")
    async def signal_delete(self) -> None:
        self._signal_count += 1
        self._delete_requested = True

    @workflow.signal(name="competitor_changed")
    async def signal_competitor_changed(self, payload: CompetitorChangedPayload) -> None:
        self._signal_count += 1
        #Preempte o timer se estiver aguardando — acorda o ciclo para nova coleta
        if self._state == WorkflowState.WaitingTimer:
            self._competitor_changed = True

    @workflow.signal(name="update_policy")
    async def signal_update_policy(self, payload: UpdatePolicySignalPayload) -> None:
        self._signal_count += 1
        self._policy_update = payload.policy
        #Se em WaitingTimer, o próximo ciclo do loop aplicará a nova política

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------

    @workflow.query(name="get_state")
    def query_get_state(self) -> WorkflowSnapshot:
        return WorkflowSnapshot(
            state=self._state,
            next_run_at=self._next_run_at,
            last_run_at=self._last_run_at,
            last_error=self._last_error,
            attempt_count=self._attempt_count,
            monitored_id=self._monitored_id,
        )

    # ------------------------------------------------------------------
    # Helpers internos
    # ------------------------------------------------------------------

    async def _sleep_preemptible(self, seconds: float) -> bool:
        """ Dorme até `seconds` ou até receber signal de preempção.

        Retorna True se foi preemptado, False se o timer expirou normalmente.
        """
        def _should_wake() -> bool:
            return (
                self._delete_requested
                or self._resume_payload is not None
                or self._pause_requested
                or self._competitor_changed
            )

        try:
            await workflow.wait_condition(_should_wake, timeout=timedelta(seconds=seconds))
            #Acordou por signal
            if self._delete_requested:
                await self._do_delete()
                return True
            if self._pause_requested:
                self._pause_requested = False
                self._state = WorkflowState.Paused
                return True
            if self._competitor_changed:
                self._competitor_changed = False
                self._state = WorkflowState.Dispatching
                return True
            if self._resume_payload is not None:
                #resume enquanto já ativo — ignora; continua timer
                self._resume_payload = None
        except asyncio.TimeoutError:
            pass  #Timer expirou normalmente

        return False

    async def _do_delete(self) -> None:
        """ Executa limpeza e transiciona para CompletedDeleted."""
        self._delete_requested = False
        await workflow.execute_activity(
            "cleanup_workflow_state",
            args=[self._monitored_id],
            start_to_close_timeout=_CLEANUP_TIMEOUT,
            retry_policy=RetryPolicy(maximum_attempts=2),
        )
        self._state = WorkflowState.CompletedDeleted

    async def _persist_snapshot(self) -> None:
        """ Persiste snapshot atual no Redis (best-effort)."""
        snapshot = self.query_get_state()
        await workflow.execute_activity(
            "persist_workflow_snapshot",
            args=[snapshot],
            start_to_close_timeout=_PERSIST_SNAPSHOT_TIMEOUT,
            retry_policy=RetryPolicy(maximum_attempts=1),
        )

    async def _continue_as_new(self) -> None:
        """ Reinicia o workflow preservando estado atual."""
        new_input = WorkflowInput(
            monitored_id=self._monitored_id,
            user_id=self._user_id,
            policy=self._policy,
            bootstrap_flags={
                "resume_state": self._state.value,
                "attempt_count": self._attempt_count,
            },
        )
        workflow.continue_as_new(new_input)
        