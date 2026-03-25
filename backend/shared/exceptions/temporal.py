"""Exceções específicas da integração com o Temporal."""


class TemporalUnavailableError(Exception):
    """Levantada quando o Temporal Server não está acessível.

    Deve ser capturada no cliente adaptador e logada como warning/error
    sem propagar para o chamador (fallback não-bloqueante).
    """

class TemporalConnectionError(Exception):
    """Levantada quando o Temporal Server não responde após todas as tentativas de conexão.

    Propagada intencionalmente para interromper o startup da API quando Temporal
    é componente crítico e não está disponível.

    Atributos:
        attempts: Número de tentativas realizadas antes de falhar.
        target:   Endereço do Temporal Server que foi tentado.
    """

    def __init__(self, message: str, *, attempts: int, target: str) -> None:
        self.attempts = attempts
        self.target = target
        super().__init__(message)

    def __str__(self) -> str:
        return (
            f"{super().__str__()} "
            f"(target={self.target!r}, attempts={self.attempts})"
        )
