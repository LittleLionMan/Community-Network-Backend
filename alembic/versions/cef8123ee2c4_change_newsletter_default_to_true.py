"""change newsletter default to true

Revision ID: cef8123ee2c4
Revises: 0310fe5e6900
Create Date: 2025-12-16 15:41:26.741349

"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "cef8123ee2c4"
down_revision: Union[str, Sequence[str], None] = "0310fe5e6900"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade():
    # existierende Daten normalisieren
    op.execute("""
        UPDATE users
        SET email_notifications_newsletter = 1
        WHERE email_notifications_newsletter IS NULL
           OR email_notifications_newsletter = 0
    """)

    with op.batch_alter_table("users") as batch_op:
        batch_op.alter_column(
            "email_notifications_newsletter",
            nullable=False,
            server_default=sa.text("1"),
        )


def downgrade():
    with op.batch_alter_table("users") as batch_op:
        batch_op.alter_column(
            "email_notifications_newsletter",
            server_default=sa.text("0"),
        )
