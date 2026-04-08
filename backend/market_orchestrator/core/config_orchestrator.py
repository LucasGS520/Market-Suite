""" Configurações centralizadas do módulo market_orchestrator """
import os
from pathlib import Path

from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings


BACKEND_DIR = Path(__file__).resolve().parents[2]
DEFAULT_ENV_FILE = Path("market_orchestrator") / ".env.market_orchestrator"
ENV_FILE = Path(os.getenv("ENV_FILE", str(DEFAULT_ENV_FILE)))
if not ENV_FILE.is_absolute():
    ENV_FILE = BACKEND_DIR / ENV_FILE


class OrchestratorSettings(BaseSettings):
    # --- Banco de dados da aplicação (mesmo DB do market_alert) ---
    DATABASE_URL: str = ""  # Deve ser definido em .env.market_orchestrator

    # --- Temporal ---
    TEMPORAL_HOST: str = "temporal"
    TEMPORAL_PORT: int = 7233
    TEMPORAL_NAMESPACE: str = "default"
    TEMPORAL_TASK_QUEUE: str = "market-orchestrator"

    # --- Workflow: limites para Continue-As-New ---
    WORKFLOW_HISTORY_LENGTH_LIMIT: int = 5000
    WORKFLOW_SIGNAL_COUNT_LIMIT: int = 500

    # --- Workflow: polling de resultado de coleta ---
    COLLECTION_RESULT_TIMEOUT_SECONDS: int = 1800  # 30 min
    COLLECTION_POLL_INTERVAL_SECONDS: int = 30

    # --- Retry policy padrão para activities ---
    RETRY_MAX_ATTEMPTS: int = 5
    RETRY_INITIAL_INTERVAL_SECONDS: int = 10
    RETRY_MAX_INTERVAL_SECONDS: int = 300  # 5 min
    RETRY_BACKOFF_COEFFICIENT: float = 2.0

    # --- Timeouts de activities (segundos) ---
    ACTIVITY_DISPATCH_TIMEOUT_SECONDS: int = 30
    ACTIVITY_QUERY_STATUS_TIMEOUT_SECONDS: int = 15
    ACTIVITY_PERSIST_SNAPSHOT_TIMEOUT_SECONDS: int = 10
    ACTIVITY_CLEANUP_TIMEOUT_SECONDS: int = 10
    ACTIVITY_FETCH_POLICY_TIMEOUT_SECONDS: int = 15

    # --- Snapshot Redis ---
    SNAPSHOT_KEY_TEMPLATE: str = "workflow:snapshot:{monitored_id}"
    SNAPSHOT_TTL_SECONDS: int = 86400  # 24 h

    @field_validator(
        "TEMPORAL_PORT",
        "WORKFLOW_HISTORY_LENGTH_LIMIT",
        "WORKFLOW_SIGNAL_COUNT_LIMIT",
        "COLLECTION_RESULT_TIMEOUT_SECONDS",
        "COLLECTION_POLL_INTERVAL_SECONDS",
        "RETRY_MAX_ATTEMPTS",
        "RETRY_INITIAL_INTERVAL_SECONDS",
        "RETRY_MAX_INTERVAL_SECONDS",
        "ACTIVITY_DISPATCH_TIMEOUT_SECONDS",
        "ACTIVITY_QUERY_STATUS_TIMEOUT_SECONDS",
        "ACTIVITY_PERSIST_SNAPSHOT_TIMEOUT_SECONDS",
        "ACTIVITY_CLEANUP_TIMEOUT_SECONDS",
        "ACTIVITY_FETCH_POLICY_TIMEOUT_SECONDS",
        "SNAPSHOT_TTL_SECONDS",
        mode="after",
    )
    @classmethod
    def must_be_positive(cls, v: int) -> int:
        if v <= 0:
            raise ValueError("Must be > 0")
        return v

    @model_validator(mode="after")
    def retry_intervals_coherent(self) -> "OrchestratorSettings":
        if self.RETRY_INITIAL_INTERVAL_SECONDS > self.RETRY_MAX_INTERVAL_SECONDS:
            raise ValueError(
                "RETRY_INITIAL_INTERVAL_SECONDS must not exceed RETRY_MAX_INTERVAL_SECONDS"
            )
        return self

    @property
    def temporal_target(self) -> str:
        return f"{self.TEMPORAL_HOST}:{self.TEMPORAL_PORT}"

    model_config = {
        "env_file": ENV_FILE,
        "env_file_encoding": "utf-8",
        "extra": "ignore",
    }


settings = OrchestratorSettings()
