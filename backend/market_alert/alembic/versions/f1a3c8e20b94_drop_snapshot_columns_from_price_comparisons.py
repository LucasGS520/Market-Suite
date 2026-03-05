"""drop snapshot columns from price_comparisons

Remove colunas de metadados do endpoint snapshot (GET /comparisons/{id}),
que foi removido em favor do endpoint summary como única fonte de verdade.
Colunas mantidas para auditoria: competitors_with_price_count, completed_at.

Revision ID: f1a3c8e20b94
Revises: e3a1f7c29d80
Create Date: 2026-03-05
"""
from typing import Union

import sqlalchemy as sa
from alembic import op

revision: str = 'f1a3c8e20b94'
down_revision: Union[str, None] = 'e3a1f7c29d80'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_column('price_comparisons', 'status')
    op.drop_column('price_comparisons', 'is_complete')
    op.drop_column('price_comparisons', 'included_competitors_count')


def downgrade() -> None:
    op.add_column('price_comparisons', sa.Column('included_competitors_count', sa.Integer(), nullable=True))
    op.add_column('price_comparisons', sa.Column('is_complete', sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column('price_comparisons', sa.Column('status', sa.String(32), nullable=True))
