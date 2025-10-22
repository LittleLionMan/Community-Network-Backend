"""add achievement

Revision ID: 2b7436b6b289
Revises: 5dbbbcf727f9
Create Date: 2025-10-08 16:48:22.546142

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import sqlite

# revision identifiers, used by Alembic.
revision: str = "2b7436b6b289"
down_revision: Union[str, Sequence[str], None] = "5dbbbcf727f9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create user_achievements table
    op.create_table(
        "user_achievements",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("achievement_type", sa.String(length=100), nullable=False),
        sa.Column("points", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("reference_type", sa.String(length=50), nullable=True),
        sa.Column("reference_id", sa.Integer(), nullable=True),
        sa.Column("awarded_by_user_id", sa.Integer(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["awarded_by_user_id"], ["users.id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id"),
    )

    # Create indexes for better query performance
    op.create_index("ix_user_achievements_user_id", "user_achievements", ["user_id"])
    op.create_index(
        "ix_user_achievements_achievement_type",
        "user_achievements",
        ["achievement_type"],
    )
    op.create_index(
        "ix_user_achievements_reference",
        "user_achievements",
        ["reference_type", "reference_id"],
    )
    op.create_index(
        "ix_user_achievements_awarded_by", "user_achievements", ["awarded_by_user_id"]
    )

    # Composite index for duplicate checking and leaderboard queries
    op.create_index(
        "ix_user_achievements_lookup",
        "user_achievements",
        ["user_id", "achievement_type", "reference_type", "reference_id"],
    )


def downgrade() -> None:
    # Drop indexes
    op.drop_index("ix_user_achievements_lookup", table_name="user_achievements")
    op.drop_index("ix_user_achievements_awarded_by", table_name="user_achievements")
    op.drop_index("ix_user_achievements_reference", table_name="user_achievements")
    op.drop_index(
        "ix_user_achievements_achievement_type", table_name="user_achievements"
    )
    op.drop_index("ix_user_achievements_user_id", table_name="user_achievements")

    # Drop table
    op.drop_table("user_achievements")
