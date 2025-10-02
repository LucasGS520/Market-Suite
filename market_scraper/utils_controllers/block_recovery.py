""" Gerencia ações de recuperação após bloqueios de scraping """

from dataclasses import dataclass
from typing import List, Optional
from urllib.parse import urlparse

import asyncio
import inspect
import structlog
import httpx

from shared.enums import BlockResult
from shared.utils.redis_client import suspend_scraping

from market_scraper.utils.humanized_delay import HumanizedDelayManager
from market_scraper.utils_controllers.session_identity import SessionIdentityManager, session_identity_manager
from market_scraper.utils.cache_adapter import cache_adapter
from market_scraper.utils.http_utils import extract_hostname
from market_scraper.utils.robots_txt import RobotsTxtManager


logger = structlog.get_logger("block_recovery")

@dataclass
class BlockRecoveryManager:
    """ Coordena etapas de recuperação quando o scraping é bloqueado

    Este gerenciador rotaciona o ``User-Agent``, reseta cookies e prolonga
    o delay de requisições. Ao final, ativa uma suspensão temporária no Redis
    utilizando ``suspend_scraping`` para evitar novas tentativas agressivas
    """
    identity_manager: Optional[SessionIdentityManager] = None
    delay_manager: HumanizedDelayManager = HumanizedDelayManager()

    #Períodos de suspensão progressivos em segundos
    suspension_steps: List[int] = (300, 900, 1800)
    _severity: int = 0

    def __post_init__(self) -> None:
        self.identity_manager = self.identity_manager or session_identity_manager

    async def handle_block(
            self,
            block_type: BlockResult,
            session_id: str | None = None,
            url: str | None = None,
    ) -> Optional[str]:
        """ Aplica ações de mitigação quando o scraping é bloqueado

        Após rotacionar recursos e suspender temporariamente o scraping,
        tenta recuperar o HTML por uma nova requisição. Se a tentativa
        direta falhar, recorre ao ``IntelligentCacheManager``.
        """
        severity_map = {
            BlockResult.HTTP_429: 1,
            BlockResult.HTTP_403: 2,
            BlockResult.CAPTCHA: 3,
        }
        level = severity_map.get(block_type, 1)

        self._severity = max(level, self._severity + 1)

        host = extract_hostname(url) if url else None

        self.identity_manager.rotate_user_agent(session_id, host=host)
        self.identity_manager.reset_cookies(session_id, host=host)
        self.delay_manager.prolong()

        session_key = session_id or "block_recovery"

        recovered_html: Optional[str] = None

        idx = min(self._severity - 1, len(self.suspension_steps) - 1)
        suspend_seconds = self.suspension_steps[idx]
        #Registra no Redis uma suspensão temporária do scraping
        suspend_scraping(suspend_seconds)

        result_log = "falha"
        if url:
            parser = RobotsTxtManager(base_url=url)
            user_agent = self.identity_manager.get_user_agent(session_key, host=host)
            path = urlparse(url).path or "/"
            if not await parser.is_allowed(path, user_agent):
                logger.warning("blocking_robots_recovery", domain=extract_hostname(url), user_agent=user_agent)
                return None
            
            delay = await parser.get_crawl_delay(user_agent)
            if delay:
                await asyncio.sleep(delay)

            headers = {"User-Agent": user_agent}
            cookies = self.identity_manager.get_cookies(session_key, host=host)
            try:
                async with httpx.AsyncClient(headers=headers, cookies=cookies, timeout=10) as client:
                    resp = await client.get(url)
                    resp.raise_for_status()
                    recovered_html = resp.text
                    self.identity_manager.update_cookies(session_key, resp, host=host)
                    result_log = "requisicao"
            except Exception:
                marketplace = extract_hostname(url)
                try:
                    #O adaptador garante compatibilidade com dados gravados antes da migração de chaves
                    cached_result = cache_adapter.get(marketplace=marketplace, url=url)
                    #Compatibilidade com adaptadroes síncronos utlizados em testes antigos
                    if inspect.isawaitable(cached_result):
                        cached_result = await cached_result
                    cached = cached_result or {}
                    recovered_html = cached.get("html")
                    if recovered_html:
                        result_log = "cache"
                except Exception:
                    recovered_html = None

        logger.info("retentativa_bloqueio", type=block_type.name, result=result_log,)

        return recovered_html

async def recover_html_if_blocked(
    url: str,
    reason: BlockResult,
    *,
    manager: BlockRecoveryManager | None = None,
    session_id: str | None = None,
) -> Optional[str]:
    """ Realiza tentativa assíncrona de recuperação do HTML

    Esta função é um atalho para utilizar o ``BlockRecoveryManager``
    sem instanciá-lo manualmente.
    """
    manager = manager or BlockRecoveryManager()
    return await manager.handle_block(reason, session_id=session_id, url=url)
