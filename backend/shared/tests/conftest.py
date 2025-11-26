""" Fixtures compartilhadas paar os testes do pacote ``shared``

Este módulo disponibiliza utilitários de teste comuns,
como uma implementação simples de Redis em memória
"""

import pytest

class FakeRedis:
    """ Implementação mínima de um cliente Redis em memória

    Esta classe armazena pares chave/valor e respectivas TTLs em dicionários
    python, permitindo que testes simulem operações básicas do Redis sem a
    necessidade de um servidor real
    """

    def __init__(self) -> None:
        #Armazena os dados definidos com ``set``
        self.store: dict[str, object] = {}
        #Armazena os tempos de expiração (TTL) associados às chaves
        self.ttl_store: dict[str, int] = {}

    def set(self, key: str, value: object, ex: int | None = None) -> None:
        """ Define um valor para a chave e registra o TTL opcional"""
        self.store[key] = value
        if ex is not None:
            self.ttl_store[key] = ex

    def ttl(self, key: str) -> int | None:
        """ Retorna o TTL de uma chave, se existir """
        return self.ttl_store.get(key)

    def incr(self, key: str) -> int:
        """ Incrementa o valor da chave e retorna o novo total """
        self.store[key] = int(self.store.get(key, 0)) + 1
        return self.store[key]

    def expire(self, key: str, ex: int) -> None:
        """ Define o TTL para uma chave """
        self.ttl_store[key] = ex

    def exists(self, key: str) -> bool:
        """ Verifica se a chave está presente no armazenamento """
        return key in self.store

    def delete(self, key: str) -> None:
        """ Remove a chave e seu TTL associado """
        self.store.pop(key, None)
        self.ttl_store.pop(key, None)

@pytest.fixture()
def fake_redis() -> FakeRedis:
    """ Retorna uma instância de ``FakeRedis`` para uso nos testes """
    return FakeRedis()
