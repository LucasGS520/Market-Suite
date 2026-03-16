"""drop_task_failures_if_exists

Revision ID: 2db89ef7de32
Revises: a1b2c3d4e5f6
Create Date: 2026-03-16 13:57:23.063085

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '2db89ef7de32'
down_revision: Union[str, None] = 'a1b2c3d4e5f6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.execute("DROP TABLE IF EXISTS public.task_failures CASCADE;")


def downgrade() -> None:
    """Downgrade schema."""
    pass
