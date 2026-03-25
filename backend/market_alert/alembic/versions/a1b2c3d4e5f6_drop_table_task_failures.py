"""drop table task_failures

Revision ID: a1b2c3d4e5f6
Revises: d4e9f1a3b7c2
Create Date: 2026-03-09

A tabela task_failures era populada pela task Celery handle_dead_letter
(fila dead_letter). Com a migração para DLQ via Redis Streams (celery:dlq),
a tabela e o worker consumidor foram removidos. Falhas permanentes agora
são registradas diretamente via XADD no stream Redis.
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision: str = "a1b2c3d4e5f6"
down_revision: Union[str, None] = "d4e9f1a3b7c2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("DROP TABLE IF EXISTS public.task_failures CASCADE;")


def downgrade() -> None:
    op.create_table(
        "task_failures",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            nullable=False,
        ),
        sa.Column("task_name", sa.String(length=255), nullable=False),
        sa.Column("task_id", sa.String(length=255), nullable=False),
        sa.Column("exception_class", sa.String(length=255), nullable=True),
        sa.Column("exception_message", sa.Text(), nullable=True),
        sa.Column("trace_id", sa.String(length=255), nullable=True),
        sa.Column("retry_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "occurred_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
