""" Rotas de saúde do serviço de scraping """

from fastapi import APIRouter

from market_scraper.collection import get_crawlee_runtime

router = APIRouter(prefix="/health", tags=["Health"])


@router.get("/ping")
async def health_check() -> dict:
    """ Retorna status do serviço e disponibilidade das camadas de aquisição.

    O campo ``playwright_fallback_ready`` indica se o browser Playwright
    está disponível. Quando ``False``, o serviço opera em modo degradado:
    anti-bot e outros cenários de SCALE retornarão 503 em vez de tentar o fallback.
    """
    return {
        "status": "ok",
        "playwright_fallback_ready": get_crawlee_runtime().browser_ready,
    }
