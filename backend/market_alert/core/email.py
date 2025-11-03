""" Envio de email simplificado para notificações. """

import structlog


#Logger utilizado para registrar os envios simulados de email. Caso a
#aplicação evolua para um serviço real de email, basta ajustar esta função.
logger = structlog.get_logger("email")

def send_email(to: str, subject: str, body: str) -> None:
    """ Abstração simples de envio de email.

    Atualmente apenas registra no log para fins de teste, mas pode ser
    substituída por uma implementação real no futuro.
    """
    #Registra a chamada para facilitar depuração e validação em testes
    logger.info("send_email", to=to, subject=subject, body=body)
