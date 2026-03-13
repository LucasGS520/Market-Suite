""" Configurações do módulo market_orchestrator """
from pydantic_settings import BaseSettings


class OrchestratorSettings(BaseSettings):
    TEMPORAL_HOST: str = "localhost"
    TEMPORAL_PORT: int = 7233
    TEMPORAL_NAMESPACE: str = "default"

    @property
    def temporal_target(self) -> str:
        return f"{self.TEMPORAL_HOST}:{self.TEMPORAL_PORT}"

    model_config = {"env_file": ".env.market_orchestrator", "extra": "ignore"}


settings = OrchestratorSettings()
