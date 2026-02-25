""" Carregamento explícito dos módulos de tasks Celery.

Celery carrega automaticamente os módulos listados em ``include`` quando
iniciado via CLI. Em outros contextos — testes, inicialização da aplicação
FastAPI, scripts — o import não ocorre automaticamente.

``load_task_modules()`` força o import de cada módulo para garantir que as
tasks estejam registradas e disponíveis, independente do contexto de execução.

Responsabilidade única:
    Importar módulos de tasks. Nenhuma lógica de negócio aqui.
"""

from importlib import import_module

import structlog

logger = structlog.get_logger("task_loader")


def load_task_modules(task_modules: list[str]) -> None:
    """ Importa explicitamente cada módulo de tasks listado.

    Em execuções fora do worker Celery (ex.: testes ou inicialização da
    aplicação), o Celery não percorre ``include`` automaticamente. Esta função
    garante que todas as tasks sejam registradas antes de qualquer chamada.

    Args:
        task_modules: Lista de caminhos de módulo Python (ex.:
            ``['market_alert.tasks.collector_product_task', ...]``) —
            normalmente vinda de ``celery_schedule.TASK_MODULES``.
    """
    failed_modules: list[str] = []
    for module_path in task_modules:
        try:
            import_module(module_path)
            logger.debug("task_module_imported", module=module_path)
        except Exception:
            failed_modules.append(module_path)
            logger.exception("task_module_import_failed", module=module_path)

    if failed_modules:
        #Interrompe startup para evitar worker/API sem tasks registradas
        raise RuntimeError(
            "Falha ao carregar módulos de tasks: " + ", ".join(failed_modules)
        )
    
    logger.info("task_modules_loaded", total=len(task_modules))
