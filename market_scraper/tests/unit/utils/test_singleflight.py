""" Executa o utilitário de singleflight garantindo execução única por chave """

from __future__ import annotations

import asyncio

import pytest

from market_scraper.utils.singleflight import AsyncSingleFlight, _SingleFlightEntry


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
    
def test_singleflight_entry_uses_existing_loop_from_get_event_loop() -> None:
    """ Garante que a entrada recupere o loop atual via ``get_event_loop`` quando necessário """
    loop = asyncio.new_event_loop()
    try:
        asyncio.set_event_loop(loop)
        entry = _SingleFlightEntry()
        assert entry.future.get_loop() is loop
    finally:
        asyncio.set_event_loop(None)
        loop.close()

def test_singleflight_entry_provides_guidance_without_configured_loop(event_loop: asyncio.AbstractEventLoop) -> None:
    """ Valida mensagem orientativa ao tentar usar o utilitário sem loop configurado """
    asyncio.set_event_loop(None)
    with pytest.raises(RuntimeError, match="AsyncSingleFlight requer um loop de eventos ativo"):
        _SingleFlightEntry()
    asyncio.set_event_loop(event_loop)
    