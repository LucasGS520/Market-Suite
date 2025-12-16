"""enums_pengind_concorrente

Revision ID: 67e3d60782f2
Revises: 2b3def4a0eae
Create Date: 2025-11-28 12:02:46.742183

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '67e3d60782f2'
down_revision: Union[str, None] = '2b3def4a0eae'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Adiciona o novo label em autocommit (necessário no Postgres)
    ctx = op.get_context()
    with ctx.autocommit_block():
        op.execute("""
        DO $$
        BEGIN
          IF NOT EXISTS (
            SELECT 1 FROM pg_type t
            JOIN pg_enum e ON t.oid = e.enumtypid
            WHERE t.typname = 'product_status_enum' AND e.enumlabel = 'pending'
          ) THEN
            ALTER TYPE product_status_enum ADD VALUE 'pending';
          END IF;
        END
        $$;
        """)

    # Agora que o label existe commitado, é seguro executar updates
    op.execute("""
    UPDATE competitor_products
      SET current_price = NULL
      WHERE current_price = 0 AND last_scraped_at IS NULL;
    UPDATE competitor_products
      SET status = 'pending'
      WHERE current_price IS NULL AND status = 'unavailable' AND last_scraped_at IS NULL;
    """)


def downgrade() -> None:
    """Downgrade schema."""
    # remover label de enum não é trivial no Postgres; manual se necessário
    pass
