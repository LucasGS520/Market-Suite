""" Contrato do pacote CRUD de produtos monitorados e concorrentes.

Este módulo não executa reexport com import eager para evitar ciclos durante o
bootstrap da API e dos workers. 
Os consumidores devem importar cada CRUD pelo caminho explícito.
"""

__all__ = ["crud_competitor", "crud_monitored", "crud_price_history"]
