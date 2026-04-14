from __future__ import annotations

import sys


def reset_shared_runtime_state() -> None:
    redis_client_module = sys.modules.get("shared.utils.redis_client")
    if redis_client_module is not None:
        thread_local = getattr(redis_client_module, "_thread_local", None)
        if thread_local is not None:
            for attr in ("client", "operational_client"):
                client = getattr(thread_local, attr, None)
                if client is not None and hasattr(client, "close"):
                    client.close()
                if hasattr(thread_local, attr):
                    delattr(thread_local, attr)
        getattr(redis_client_module, "_registered_scripts", {}).clear()
        getattr(redis_client_module, "_registered_token_bucket_scripts", {}).clear()

    task_dispatcher_module = sys.modules.get("shared.clients.celery.task_dispatcher")
    if task_dispatcher_module is not None:
        task_dispatcher_module._sender = None

    scraper_client_module = sys.modules.get("shared.clients.scraper.scraper_client")
    if scraper_client_module is not None:
        scraper_client_module._rate_limiter_inst = None
        scraper_client_module._circuit_breaker_inst = None

    temporal_client_module = sys.modules.get("shared.clients.temporal.orchestrator_client")
    if temporal_client_module is not None:
        temporal_client_module._client_instance = None

    database_module = sys.modules.get("shared.infra.db.database")
    if database_module is not None:
        engine = getattr(database_module, "engine", None)
        if engine is not None and hasattr(engine, "dispose"):
            engine.dispose()


def reset_market_alert_runtime_state() -> None:
    reset_shared_runtime_state()

    bruteforce_module = sys.modules.get("market_alert.infrastructure.security.bruteforce")
    if bruteforce_module is None:
        return

    redis_client = None
    redis_client_module = sys.modules.get("shared.utils.redis_client")
    if redis_client_module is not None:
        get_redis_operational = getattr(redis_client_module, "get_redis_operational", None)
        if callable(get_redis_operational):
            try:
                redis_client = get_redis_operational()
            except Exception:
                redis_client = None

    bruteforce_module.redis_client = redis_client


def reset_market_orchestrator_runtime_state() -> None:
    reset_shared_runtime_state()
