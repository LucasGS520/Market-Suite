""" Rotas de saúde do serviço de scraping """

from fastapi import APIRouter

router = APIRouter(prefix="/health", tags=["Health"])


@router.get("/ping")
async def health_check() -> dict:
    """ Retorna um status indicando que o serviço está ativo """
    return {"status": "ok"}
