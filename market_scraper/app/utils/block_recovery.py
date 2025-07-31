""" Gerencia ações de recuperação após bloqueios de scraping """

from dataclasses import dataclass
from typing import List, Optional

import structlog

from app.utils.humanized_delay import HumanizedDelayManager
from app.utils.redis_client import suspend_scraping, get_redis_client
from app.utils.user_agent_manager import IntelligentUserAgentManager
from app.utils.cookie_manager import CookieManager
from app.utils.playwright_client import get_playwright_client
import app.metrics as metrics


logger = structlog.get_logger("block_recovery")

@dataclass
class BlockRecoveryManager:
    """ Coordena etapas de recuperação quando o scraping é bloqueado """
    ua_manager: Optional[IntelligentUserAgentManager] = None
    cookie_manager: Optional[CookieManager] = None
    delay_manager: HumanizedDelayManager = HumanizedDelayManager()
    redis = get_redis_client()

    suspension_steps: List[int] = (300, 900, 1800)
    _severity: int = 0

    def __post_init__(self) -> None:
        self.ua_manager = self.ua_manager or IntelligentUserAgentManager()
        self.cookie_manager = self.cookie_manager or CookieManager()

    async def handle_block(self, block_type: str, session_id: str | None = None, url: str | None = None) -> Optional[str]:
        """ Aplica ações de mitigação e tenta recuperar o HTML via navegador

        Se ``url`` for informado e o bloqueio indicar ``403`` ou ``captcha``,
        a função tenta obter o HTML utilizando o Playwright de forma assíncrona.
        """
        severity_map = {"429": 1, "403": 2, "captcha": 3}
        level = severity_map.get(block_type, 1)

        self._severity = max(level, self._severity + 1)

        self.ua_manager.rotate(session_id)
        self.cookie_manager.reset(session_id)
        self.delay_manager.prolong()

        recovered_html: Optional[str] = None

        if block_type in {"captcha", "403"} and url:
            try:
                async with get_playwright_client() as client:
                    recovered_html = await client.fetch_html(
                        url, session_id=session_id
                    )
                metrics.SCRAPER_BROWSER_RECOVERY_SUCCESS_TOTAL.inc()
            except Exception as exc:
                logger.warning("browser_fallback_failed", url=url, error=str(exc))

        idx = min(self._severity - 1, len(self.suspension_steps) - 1)
        suspend_seconds = self.suspension_steps[idx]
        suspend_scraping(suspend_seconds)

        return recovered_html

async def recover_html_if_blocked(
    url: str,
    reason: str,
    *,
    manager: BlockRecoveryManager | None = None,
    session_id: str | None = None
) -> Optional[str]:
    """ Realiza tentativa assíncrona de recuperação do HTML

    Esta função é um atalho para utilizar o ``BlockRecoveryManager``
    sem instanciá-lo manualmente.
    """
    manager = manager or BlockRecoveryManager()
    return await manager.handle_block(reason, session_id=session_id, url=url)
