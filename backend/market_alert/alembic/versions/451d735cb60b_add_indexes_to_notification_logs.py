"""add indexes to notification logs

Revision ID: 451d735cb60b
Revises: 5e41b7f3a907
Create Date: 2025-07-07 16:36:04.933576

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '451d735cb60b'
down_revision: Union[str, None] = '5e41b7f3a907'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema by adding indexes used in log queries."""
    op.create_index(
        op.f("ix_notification_logs_sent_at"),
        "notification_logs",
        ["sent_at"],
        unique=False,
    )
    op.create_index(
        op.f("ix_notification_logs_channel"),
        "notification_logs",
        ["channel"],
        unique=False,
    )
    op.create_index(
        op.f("ix_notification_logs_success"),
        "notification_logs",
        ["success"],
        unique=False,
    )


def downgrade() -> None:
    """Remove indexes from notification logs."""
    op.drop_index(op.f("ix_notification_logs_success"), table_name="notification_logs")
    op.drop_index(op.f("ix_notification_logs_channel"), table_name="notification_logs")
    op.drop_index(op.f("ix_notification_logs_sent_at"), table_name="notification_logs")
