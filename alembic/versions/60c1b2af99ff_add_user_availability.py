"""add_user_availability

Revision ID: 60c1b2af99ff
Revises: 630fa896e3bf
Create Date: 2025-12-02 16:44:29.062404

"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "60c1b2af99ff"
down_revision: Union[str, Sequence[str], None] = "630fa896e3bf"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "user_availability",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column(
            "slot_type",
            sa.String(length=20),
            nullable=False,
            server_default="available",
        ),
        sa.Column("day_of_week", sa.Integer(), nullable=True),
        sa.Column("start_time", sa.Time(), nullable=True),
        sa.Column("end_time", sa.Time(), nullable=True),
        sa.Column("specific_date", sa.Date(), nullable=True),
        sa.Column("specific_start", sa.DateTime(timezone=True), nullable=True),
        sa.Column("specific_end", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "source", sa.String(length=50), nullable=False, server_default="manual"
        ),
        sa.Column("source_id", sa.Integer(), nullable=True),
        sa.Column("title", sa.String(length=200), nullable=True),
        sa.Column("notes", sa.String(length=500), nullable=True),
        sa.Column(
            "is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_index(
        "idx_availability_user", "user_availability", ["user_id", "is_active"]
    )
    op.create_index("idx_availability_date", "user_availability", ["specific_date"])
    op.create_index(
        "idx_availability_source", "user_availability", ["source", "source_id"]
    )


def downgrade() -> None:
    op.drop_index("idx_availability_source", table_name="user_availability")
    op.drop_index("idx_availability_date", table_name="user_availability")
    op.drop_index("idx_availability_user", table_name="user_availability")
    op.drop_table("user_availability")
