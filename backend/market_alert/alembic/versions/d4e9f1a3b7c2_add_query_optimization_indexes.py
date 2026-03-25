"""add query optimization indexes

Revision ID: d4e9f1a3b7c2
Revises: f1a3c8e20b94
Create Date: 2026-03-06

Adiciona índices compostos para otimizar consultas de leitura frequentes:
  - price_history (monitored_product_id, checked_at DESC) — parcial: monitorados
  - price_history (competitor_product_id, checked_at DESC) — parcial: concorrentes
  - price_comparisons (monitored_product_id, timestamp DESC)
  - price_comparison_summaries (monitored_product_id, timestamp DESC)
  - notifications (user_id, status, created_at DESC)
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = 'd4e9f1a3b7c2'
down_revision: Union[str, None] = 'f1a3c8e20b94'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # price_history: índices compostos parciais para evitar linhas nulas no prefix
    op.create_index(
        'ix_price_history_monitored_checked_at',
        'price_history',
        ['monitored_product_id', sa.text('checked_at DESC')],
        postgresql_where=sa.text('monitored_product_id IS NOT NULL'),
    )
    op.create_index(
        'ix_price_history_competitor_checked_at',
        'price_history',
        ['competitor_product_id', sa.text('checked_at DESC')],
        postgresql_where=sa.text('competitor_product_id IS NOT NULL'),
    )

    # price_comparisons: consultas por produto ordenadas por timestamp
    op.create_index(
        'ix_price_comparisons_monitored_timestamp',
        'price_comparisons',
        ['monitored_product_id', sa.text('timestamp DESC')],
    )

    # price_comparison_summaries: consultas por produto ordenadas por timestamp
    op.create_index(
        'ix_price_comparison_summaries_monitored_timestamp',
        'price_comparison_summaries',
        ['monitored_product_id', sa.text('timestamp DESC')],
    )

    # notifications: consultas de entrega por usuário filtradas por status
    op.create_index(
        'ix_notifications_user_status_created_at',
        'notifications',
        ['user_id', 'status', sa.text('created_at DESC')],
    )


def downgrade() -> None:
    op.drop_index('ix_notifications_user_status_created_at', table_name='notifications')
    op.drop_index('ix_price_comparison_summaries_monitored_timestamp', table_name='price_comparison_summaries')
    op.drop_index('ix_price_comparisons_monitored_timestamp', table_name='price_comparisons')
    op.drop_index('ix_price_history_competitor_checked_at', table_name='price_history')
    op.drop_index('ix_price_history_monitored_checked_at', table_name='price_history')
