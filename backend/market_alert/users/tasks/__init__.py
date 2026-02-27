""" Tasks relacionadas a configurações do usuário 

As tasks exportadas aqui representam os gatilhos assíncronos estáveis
para envio de verificações de identidade.
"""

from market_alert.users.tasks.verification_tasks import (
    send_email_verification,
    send_phone_otp,
)

__all__ = ["send_email_verification", "send_phone_otp"]
