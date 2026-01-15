""" Enumerações relacionadas ao cadastro e status de usuários """

from enum import Enum


class UserStatus(str, Enum):
    """ Estados possíveis para a conta de um usuário """
    pending = "PENDING" #Conta criada, aguardando verificação
    active = "ACTIVE" #Conta ativa e verificada pronta para uso
    suspended = "SUSPENDED" #Conta suspensa por violação de termos ou inatividade

class VerificationKind(str, Enum):
    """ Tipos de verificação suportados no cadastro """
    email = "email" #Verificação via link enviado por email
    phone_number = "phone_number" #Verificação via OTP enviado por telefone


__all__ = ["UserStatus", "VerificationKind"]
