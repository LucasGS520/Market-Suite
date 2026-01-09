""" Métricas relacionadas à autenticação de usuários """

from prometheus_client import Counter

LOGIN_ERRORS_TOTAL = Counter(
    "login_errors_total",
    "Total de erros de autenticação",
    ["reason"],
)
VERIFICATION_SENT_TOTAL = Counter(
    "verification_sent_total",
    "Total de tokens de verificação enviados",
    ["channel"],
)
VERIFICATION_RESEND_ATTEMPTS_TOTAL = Counter(
    "verification_resend_attempts_total",
    "Total de tentativas de reenvio de verificação",
    ["channel"],
)
VERIFICATION_SUCCESS_TOTAL = Counter(
    "verification_success_total",
    "Total de verificações concluídas com sucesso",
    ["channel"],
)
VERIFICATION_FAILURE_TOTAL = Counter(
    "verification_failure_total",
    "Total de falhas no fluxo de verificação",
    ["channel", "reason"],
)

__all__ = [
    "LOGIN_ERRORS_TOTAL",
    "VERIFICATION_SENT_TOTAL",
    "VERIFICATION_RESEND_ATTEMPTS_TOTAL",
    "VERIFICATION_SUCCESS_TOTAL",
    "VERIFICATION_FAILURE_TOTAL",
]
