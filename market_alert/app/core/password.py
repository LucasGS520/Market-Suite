""" Utilidades para hashing e verificação de senhas """

import bcrypt


def hash_password(plain_password: str) -> bytes:
    """ Retorna senha criptografada como binário """
    #Gera hash utilizando sal aleatório do bcrypt
    return bcrypt.hashpw(plain_password.encode('utf-8'), bcrypt.gensalt())

def verify_password(plain_password: str, hashed_password: bytes) -> bool:
    """ Compara senha informada com hash armazenado """
    #Comparação segura entre a senha digitada e o hash salvo
    return bcrypt.checkpw(plain_password.encode('utf-8'), hashed_password)
