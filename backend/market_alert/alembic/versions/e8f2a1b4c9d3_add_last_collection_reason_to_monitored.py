"""add last_collection_reason to monitored_products

Persiste o motivo tipado da ultima coleta (ex: http_429, challenge_detected)
para permitir que a camada de comparacao propague upstream_reason especifico
em vez de apenas "upstream_collection_failed" generico.

Revision ID: e8f2a1b4c9d3
Revises: d4e9f1a3b7c2
Create Date: 2026-04-13
"""

from typing import Union

import sqlalchemy as sa
from alembic import op


revision: str = 'e8f2a1b4c9d3'
down_revision: Union[str, None] = '2db89ef7de32'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        'monitored_products',
        sa.Column('last_collection_reason', sa.String(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column('monitored_products', 'last_collection_reason')
