""" Remove campos checking_in_progress e checking_started_at

Revision ID: f8d9e2a1b3c4
Revises: 451d735cb60b
Create Date: 2025-12-12 12:56:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'f8d9e2a1b3c4'
down_revision: Union[str, None] = '451d735cb60b'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """ Remove campos obsoletos de controle de rechecagem inline.
    
    O novo fluxo simplificado usa apenas locks Redis para controle de
    concorrência, eliminando a necessidade de flags no banco de dados.
    """
    #Remove coluna checking_in_progress
    op.drop_column('monitored_products', 'checking_in_progress')
    
    #Remove coluna checking_started_at
    op.drop_column('monitored_products', 'checking_started_at')


def downgrade() -> None:
    """ Restaura campos removidos caso seja necessário reverter.
    
    A reversão mantém compatibilidade com o código legado, mas não é
    recomendada após a migração para o novo fluxo simplificado.
    """
    #Recria coluna checking_started_at
    op.add_column(
        'monitored_products',
        sa.Column(
            'checking_started_at',
            postgresql.TIMESTAMP(timezone=True),
            nullable=True,
        )
    )
    
    #Recria coluna checking_in_progress com valor padrão
    op.add_column(
        'monitored_products',
        sa.Column(
            'checking_in_progress',
            sa.Boolean(),
            nullable=False,
            server_default='false',
        )
    )
