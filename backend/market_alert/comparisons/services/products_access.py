""" Acesso intermediário a monitorados e concorrentes para serviços de comparação.

Este módulo centraliza leituras de dados que antes eram importadas diretamente
em serviços de comparação. A decisão é arquitetural: encapsular imports locais
(lazy) dos CRUDs para evitar dependência circular durante o startup da aplicação.
"""

from uuid import UUID

from sqlalchemy.orm import Session


def get_monitored_by_id(
    db: Session,
    monitored_id: UUID
):
    """ Obtém um produto monitorado pelo identificador.

    O import do CRUD é feito apenas no momento da chamada para evitar ciclos de
    importação entre módulos de produtos e comparação durante a carga inicial.
    """
    #Import local (lazy) para reduzir acoplamento de tempo de import.
    from market_alert.products.crud import crud_monitored

    return crud_monitored.get_monitored_product_by_id(db, monitored_id)

def get_competitors_for_monitored(
    db: Session,
    monitored_id: UUID,
    *,
    include_paused: bool = False,
    include_inactive: bool = False,
):
    """ Lista concorrentes associados a um monitorados.
    
    Mantém o acesso encapsulado para que o serviço consumidor não dependa
    de CRUDs diretamente, preservando a barreira arquitetural anti-ciclo.
    """
    #Import local (lazy) para evitar dependência circular no startup
    from market_alert.products.crud import crud_competitor

    return crud_competitor.get_competitors_by_monitored_id(
        db,
        monitored_id,
        include_paused=include_paused,
        include_inactive=include_inactive,
    )
