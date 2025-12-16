"""add_exact_address_and_cleanup_locations

Revision ID: ff046572c3b9
Revises: 54cb31667c3c
Create Date: 2025-12-12 17:47:31.385569

"""

from typing import Sequence, Union

import sqlalchemy as sa
from sqlalchemy.dialects import sqlite

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "ff046572c3b9"
down_revision: Union[str, Sequence[str], None] = "54cb31667c3c"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade():
    # 1. Rename users.location -> users.exact_address (mit batch für SQLite)
    with op.batch_alter_table("users", schema=None) as batch_op:
        batch_op.alter_column(
            "location",
            new_column_name="exact_address",
            existing_type=sa.String(200),
            type_=sa.String(500),  # Erweitere gleichzeitig auf 500
            nullable=True,
        )

    # 2. Add exact_address to book_offers
    op.add_column(
        "book_offers", sa.Column("exact_address", sa.String(500), nullable=True)
    )

    # 3. Remove location fields from exchange_transactions (mit batch für SQLite)
    with op.batch_alter_table("exchange_transactions", schema=None) as batch_op:
        batch_op.drop_column("exact_address")
        batch_op.drop_column("location_district")


def downgrade():
    # Reverse operations
    with op.batch_alter_table("users", schema=None) as batch_op:
        batch_op.alter_column(
            "exact_address",
            new_column_name="location",
            existing_type=sa.String(500),
            type_=sa.String(200),
            nullable=True,
        )

    op.drop_column("book_offers", "exact_address")

    with op.batch_alter_table("exchange_transactions", schema=None) as batch_op:
        batch_op.add_column(sa.Column("exact_address", sa.String(500), nullable=True))
        batch_op.add_column(
            sa.Column("location_district", sa.String(200), nullable=True)
        )
