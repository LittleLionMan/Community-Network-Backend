"""add_notification_privacy_settings

Revision ID: 5dbbbcf727f9
Revises: de0f70fd9ff6
Create Date: 2025-10-07 08:07:18.764895

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "5dbbbcf727f9"
down_revision: Union[str, Sequence[str], None] = "de0f70fd9ff6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add notification privacy columns to users table
    # Using batch mode for SQLite compatibility
    with op.batch_alter_table("users", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column(
                "notification_forum_reply",
                sa.Boolean(),
                nullable=False,
                server_default=sa.text("true"),
            )
        )
        batch_op.add_column(
            sa.Column(
                "notification_forum_mention",
                sa.Boolean(),
                nullable=False,
                server_default=sa.text("true"),
            )
        )
        batch_op.add_column(
            sa.Column(
                "notification_forum_quote",
                sa.Boolean(),
                nullable=False,
                server_default=sa.text("true"),
            )
        )


def downgrade() -> None:
    # Remove notification privacy columns
    # Using batch mode for SQLite compatibility
    with op.batch_alter_table("users", schema=None) as batch_op:
        batch_op.drop_column("notification_forum_quote")
        batch_op.drop_column("notification_forum_mention")
        batch_op.drop_column("notification_forum_reply")
