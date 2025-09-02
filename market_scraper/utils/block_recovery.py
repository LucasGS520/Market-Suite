""" Gerencia ações de recuperação após bloqueios de scraping """

from dataclasses import dataclass
from typing import List, Optional

import structlog

from shared.enums import BlockResult
from shared.utils.redis_client import suspend_scraping

from market_scraper.utils.humanized_delay import HumanizedDelayManager
from market_scraper.utils.user_agent_manager import IntelligentUserAgentManager
from market_scraper.utils.cookie_manager import CookieManager


logger = structlog.get_logger("block_recovery")

@dataclass
class BlockRecoveryManager:
    """ Coordena etapas de recuperação quando o scraping é bloqueado

    Este gerenciador rotaciona o ``User-Agent``, reseta cookies e prolonga
    o delay de requisições. Ao final, ativa uma suspensão temporária no Redis
    utilizando ``suspend_scraping`` para evitar novas tentativas agressivas
    """
    ua_manager: Optional[IntelligentUserAgentManager] = None
    cookie_manager: Optional[CookieManager] = None
    delay_manager: HumanizedDelayManager = HumanizedDelayManager()

    #Períodos de suspensão progressivos em segundos
    suspension_steps: List[int] = (300, 900, 1800)
    _severity: int = 0

    def __post_init__(self) -> None:
        self.ua_manager = self.ua_manager or IntelligentUserAgentManager()
        self.cookie_manager = self.cookie_manager or CookieManager()

    async def handle_block(self, block_type: BlockResult, session_id: str | None = None, url: str | None = None) -> Optional[str]:
        """ Aplica ações de mitigação quando o scraping é bloqueado """
        severity_map = {
            BlockResult.HTTP_429: 1,
            BlockResult.HTTP_403: 2,
            BlockResult.CAPTCHA: 3,
        }
        level = severity_map.get(block_type, 1)

        self._severity = max(level, self._severity + 1)

        self.ua_manager.rotate(session_id)
        self.cookie_manager.reset(session_id)
        self.delay_manager.prolong()

        recovered_html: Optional[str] = None

        idx = min(self._severity - 1, len(self.suspension_steps) - 1)
        suspend_seconds = self.suspension_steps[idx]
        #Registra no Redis uma suspensão temporária do scraping
        suspend_scraping(suspend_seconds)

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
