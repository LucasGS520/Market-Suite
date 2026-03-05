"""add snapshot metadata to price_comparisons

Revision ID: e3a1f7c29d80
Revises: 10634b0b9e93
Create Date: 2026-03-05

Adiciona metadados de snapshot à tabela price_comparisons para
permitir que GET /comparisons/{monitored_id} retorne status e
contagens sem descompactar o JSON do campo data.

Colunas adicionadas:
  - status (varchar 32, nullable) — "processing" | "complete" | "incomplete"
  - is_complete (boolean, not null, default false)
  - included_competitors_count (integer, nullable)
  - competitors_with_price_count (integer, nullable)
  - completed_at (timestamptz, nullable) — definido pelo worker na finalização
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = 'e3a1f7c29d80'
down_revision: Union[str, None] = '10634b0b9e93'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('price_comparisons', sa.Column('status', sa.String(32), nullable=True))
    op.add_column('price_comparisons', sa.Column('is_complete', sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column('price_comparisons', sa.Column('included_competitors_count', sa.Integer(), nullable=True))
    op.add_column('price_comparisons', sa.Column('competitors_with_price_count', sa.Integer(), nullable=True))
    op.add_column('price_comparisons', sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column('price_comparisons', 'completed_at')
    op.drop_column('price_comparisons', 'competitors_with_price_count')
    op.drop_column('price_comparisons', 'included_competitors_count')
    op.drop_column('price_comparisons', 'is_complete')
    op.drop_column('price_comparisons', 'status')
