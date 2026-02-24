""" fix typo ocurred_at to occurred_at

Revision ID: b7e2f914a3d1
Revises: 2f1cbfbf42f9
Create Date: 2026-02-24

Corrige o typo no campo da tabela event_log:
  ocurred_at → occurred_at (adicionado o 'r' faltante)
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op


revision: str = 'b7e2f914a3d1'
down_revision: Union[str, None] = '2f1cbfbf42f9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column("event_log", "ocurred_at", new_column_name="occurred_at")


def downgrade() -> None:
    op.alter_column("event_log", "occurred_at", new_column_name="ocurred_at")
