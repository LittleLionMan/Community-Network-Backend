"""add location_district to transactions

Revision ID: 54cb31667c3c
Revises: 7f8a9b0c1d2e
Create Date: 2025-12-12 12:14:31.376506

"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "54cb31667c3c"
down_revision: Union[str, Sequence[str], None] = "7f8a9b0c1d2e"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    conn = op.get_bind()
    dialect = conn.dialect.name

    op.add_column(
        "exchange_transactions",
        sa.Column("location_district", sa.String(length=200), nullable=True),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("exchange_transactions", "location_district")
