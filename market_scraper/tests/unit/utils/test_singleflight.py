""" Executa o utilitário de singleflight garantindo execução única por chave """

from __future__ import annotations

import asyncio

import pytest

from market_scraper.utils.singleflight import AsyncSingleFlight


@pytest.mark.asyncio
async def test_singleflight_coalesces_calls_for_same_key() -> None:
    """ Verifica que múltiplas chamadas simultâneas compartilham o mesmo resultado """
    controller = AsyncSingleFlight(lock_ttl=5.0)
    call_count = 0

    async def producer() -> str:
        nonlocal call_count
        call_count += 1
        await asyncio.sleep(0.01)
        return "<html>conteudo</html>"
    
    results = await asyncio.gather(
        controller.coalesce("https://exemplo.com/produto", producer),
        controller.coalesce("https://exemplo.com/produto", producer),
        controller.coalesce("https://exemplo.com/produto", producer),
    )

    assert call_count == 1
    assert results == ["<html>conteudo</html>"] * 3
    