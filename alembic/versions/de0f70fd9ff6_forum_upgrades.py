"""forum_upgrades

Revision ID: de0f70fd9ff6
Revises: b9785c6f0a78
Create Date: 2025-10-01 13:05:29.554453

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import sqlite

# revision identifiers, used by Alembic.
revision: str = "de0f70fd9ff6"
down_revision: Union[str, Sequence[str], None] = "b9785c6f0a78"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ========== 1. Forum Posts: Add Quotes & Mentions ==========

    # SQLite requires batch mode for FK operations
    with op.batch_alter_table("forum_posts", schema=None) as batch_op:
        # Add quoted_post_id column
        batch_op.add_column(sa.Column("quoted_post_id", sa.Integer(), nullable=True))

        # Add foreign key (self-referential)
        batch_op.create_foreign_key(
            "fk_forum_posts_quoted_post_id",
            "forum_posts",
            ["quoted_post_id"],
            ["id"],
            ondelete="SET NULL",
        )

        # Add mentioned_user_ids as JSON
        batch_op.add_column(sa.Column("mentioned_user_ids", sa.JSON(), nullable=True))

        # Add index
        batch_op.create_index("ix_forum_posts_quoted_post_id", ["quoted_post_id"])

    # ========== 2. Notifications Table ==========

    op.create_table(
        "notifications",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("type", sa.String(50), nullable=False),
        sa.Column(
            "is_read", sa.Boolean(), default=False, nullable=False, server_default="0"
        ),
        sa.Column("data", sa.JSON(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
    )

    # Notification indexes
    op.create_index(
        "ix_notifications_user_id_is_read", "notifications", ["user_id", "is_read"]
    )

    op.create_index("ix_notifications_created_at", "notifications", ["created_at"])

    # ========== 3. Forum Thread Views (Unread Tracking) ==========

    op.create_table(
        "forum_thread_views",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("thread_id", sa.Integer(), nullable=False),
        sa.Column(
            "last_viewed_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["thread_id"], ["forum_threads.id"], ondelete="CASCADE"
        ),
        sa.UniqueConstraint("user_id", "thread_id", name="uq_user_thread"),
    )

    # Thread view indexes
    op.create_index("ix_forum_thread_views_user_id", "forum_thread_views", ["user_id"])

    op.create_index(
        "ix_forum_thread_views_thread_id", "forum_thread_views", ["thread_id"]
    )


def downgrade() -> None:
    # Drop in reverse order

    # 3. Drop forum_thread_views
    op.drop_index("ix_forum_thread_views_thread_id", table_name="forum_thread_views")
    op.drop_index("ix_forum_thread_views_user_id", table_name="forum_thread_views")
    op.drop_table("forum_thread_views")

    # 2. Drop notifications
    op.drop_index("ix_notifications_created_at", table_name="notifications")
    op.drop_index("ix_notifications_user_id_is_read", table_name="notifications")
    op.drop_table("notifications")

    # 1. Drop forum_posts columns (SQLite batch mode)
    with op.batch_alter_table("forum_posts", schema=None) as batch_op:
        batch_op.drop_index("ix_forum_posts_quoted_post_id")
        batch_op.drop_constraint("fk_forum_posts_quoted_post_id", type_="foreignkey")
        batch_op.drop_column("mentioned_user_ids")
        batch_op.drop_column("quoted_post_id")
