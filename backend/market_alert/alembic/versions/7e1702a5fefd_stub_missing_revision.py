"""stub para revisão ausente 7e1702a5fefd

Revision ID: 7e1702a5fefd
Revises: 2265c00ed4a6
Create Date: 2025-12-29 14:40:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '7e1702a5fefd'
down_revision: Union[str, None] = '2265c00ed4a6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema stub (nenhuma alteração)."""
    # revisão stub criada para restaurar histórico de migrações ausente
    pass


def downgrade() -> None:
    """Downgrade schema stub (nenhuma alteração)."""
    pass
