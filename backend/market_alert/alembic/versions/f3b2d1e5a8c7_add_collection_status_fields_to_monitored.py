"""add collection status fields to monitored_products

Adiciona campos de estado semântico de coleta para fechar o contrato
ponta a ponta entre coletor, API e UI, eliminando dependência de heurísticas
parciais (ausência de last_scraped_at + preço nulo).

Campos adicionados:
- collection_outcome: outcome canônico da última tentativa (success, error, etc.)
- collection_error_class: classe semântica (transient, structural, domain_empty, neutral)
- collection_retryable: se haverá nova tentativa automática
- collection_next_retry_at: próxima tentativa agendada
- collection_source_integrity: se a origem foi íntegra para confiar no resultado
- collection_status_updated_at: quando este estado foi registrado

Nota: last_collection_reason (já existente) permanece como campo de compatibilidade.
Todos os novos campos são nullable com default NULL para retrocompatibilidade.

Revision ID: f3b2d1e5a8c7
Revises: e8f2a1b4c9d3
Create Date: 2026-04-14
"""

from typing import Union

import sqlalchemy as sa
from alembic import op


revision: str = 'f3b2d1e5a8c7'
down_revision: Union[str, None] = 'e8f2a1b4c9d3'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        'monitored_products',
        sa.Column('collection_outcome', sa.String(), nullable=True),
    )
    op.add_column(
        'monitored_products',
        sa.Column('collection_error_class', sa.String(), nullable=True),
    )
    op.add_column(
        'monitored_products',
        sa.Column('collection_retryable', sa.Boolean(), nullable=True),
    )
    op.add_column(
        'monitored_products',
        sa.Column('collection_next_retry_at', sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        'monitored_products',
        sa.Column('collection_source_integrity', sa.Boolean(), nullable=True),
    )
    op.add_column(
        'monitored_products',
        sa.Column('collection_status_updated_at', sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column('monitored_products', 'collection_status_updated_at')
    op.drop_column('monitored_products', 'collection_source_integrity')
    op.drop_column('monitored_products', 'collection_next_retry_at')
    op.drop_column('monitored_products', 'collection_retryable')
    op.drop_column('monitored_products', 'collection_error_class')
    op.drop_column('monitored_products', 'collection_outcome')
