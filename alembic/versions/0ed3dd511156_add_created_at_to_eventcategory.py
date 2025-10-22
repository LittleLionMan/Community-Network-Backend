"""Add created_at to EventCategory

Revision ID: 0ed3dd511156
Revises: 1cd37ddfc236
Create Date: 2025-09-12 20:16:06.259783

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.sql import func


# revision identifiers, used by Alembic.
revision: str = '0ed3dd511156'
down_revision: Union[str, Sequence[str], None] = '1cd37ddfc236'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = [col['name'] for col in inspector.get_columns('event_categories')]

    if 'created_at' not in columns:
        # Add created_at column if it doesn't exist
        op.add_column('event_categories',
            sa.Column('created_at',
                     sa.DateTime(timezone=True),
                     server_default=func.now(),
                     nullable=False
            )
        )
    else:
        # Column exists but might have wrong type - SQLite workaround
        # For SQLite, we can't alter column types easily, so we leave it as is
        print("Column 'created_at' already exists - skipping")

def downgrade() -> None:
    # Remove created_at column
    op.drop_column('event_categories', 'created_at')
