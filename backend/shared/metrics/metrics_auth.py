""" Métricas relacionadas à autenticação de usuários """

import os

# Importa Counter apropriado baseado em ENABLE_METRICS
_ENABLE_METRICS = os.getenv("ENABLE_METRICS", "0") in {"1", "true", "True", "yes"}
if _ENABLE_METRICS:
    import os

# Importa métricas apropriadas baseado em ENABLE_METRICS
_ENABLE_METRICS = os.getenv("ENABLE_METRICS", "0") in {"1", "true", "True", "yes"}
if _ENABLE_METRICS:
    from prometheus_client import Counter
else:
    from shared.metrics_noop import Counter
else:
    from shared.metrics_noop import Counter

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
REFRESH_MISSING_TOTAL = Counter(
    "refresh_missing_total",
    "Total de refresh tokens ausentes nas requisições de renovação",
)
REFRESH_SUCCESS_TOTAL = Counter(
    "refresh_success_total",
    "Total de renovações de access token com sucesso",
)
REFRESH_FAILURE_TOTAL = Counter(
    "refresh_failure_total",
    "Total de falhas ao renovar tokens de acesso",
    ["reason"],
)

__all__ = [
    "LOGIN_ERRORS_TOTAL",
    "VERIFICATION_SENT_TOTAL",
    "VERIFICATION_RESEND_ATTEMPTS_TOTAL",
    "VERIFICATION_SUCCESS_TOTAL",
    "VERIFICATION_FAILURE_TOTAL",
    "REFRESH_MISSING_TOTAL",
    "REFRESH_SUCCESS_TOTAL",
    "REFRESH_FAILURE_TOTAL",
]
