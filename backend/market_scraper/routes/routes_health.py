""" Rotas de saúde do serviço de scraping """

from fastapi import APIRouter

from market_scraper.infra.browser.playwright_pool import playwright_pool

router = APIRouter(prefix="/health", tags=["Health"])


@router.get("/ping")
async def health_check() -> dict:
    """ Retorna status do serviço e disponibilidade das camadas de aquisição.

    O campo ``playwright_fallback_ready`` indica se a Camada 3 (Chromium headless)
    está disponível. Quando ``False``, o serviço opera em modo degradado: anti-bot
    e outros cenários de SCALE retornarão 503 em vez de tentar o fallback.
    """
    return {
        "status": "ok",
        "playwright_fallback_ready": playwright_pool.is_ready,
    }
