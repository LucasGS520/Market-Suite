""" Métricas relacionadas à autenticação de usuários """

from prometheus_client import Counter

LOGIN_ERRORS_TOTAL = Counter(
    "login_errors_total",
    "Total de erros de autenticação",
    ["reason"],
)

__all__ = ["LOGIN_ERRORS_TOTAL"]
