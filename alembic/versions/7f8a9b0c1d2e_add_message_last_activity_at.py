"""Add last_activity_at to messages

Revision ID: 7f8a9b0c1d2e
Revises: 60c1b2af99ff
Create Date: 2025-12-03 14:30:00.000000

"""

from typing import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "7f8a9b0c1d2e"
down_revision: str | Sequence[str] | None = "60c1b2af99ff"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    conn = op.get_bind()
    dialect = conn.dialect.name

    # Spalte hinzufügen (nullable für Migration)
    op.add_column(
        "messages",
        sa.Column(
            "last_activity_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
    )

    # Existierende Rows: last_activity_at = created_at
    # SQLite und PostgreSQL kompatibel
    op.execute(
        """
        UPDATE messages
        SET last_activity_at = created_at
        WHERE last_activity_at IS NULL
        """
    )

    # Jetzt non-nullable machen
    # SQLite benötigt batch_alter_table
    if dialect == "sqlite":
        with op.batch_alter_table("messages") as batch_op:
            batch_op.alter_column(
                "last_activity_at",
                existing_type=sa.DateTime(timezone=True),
                nullable=False,
            )
    else:
        op.alter_column("messages", "last_activity_at", nullable=False)

    # Index erstellen
    op.create_index(
        "idx_messages_last_activity",
        "messages",
        ["conversation_id", "last_activity_at"],
    )


def downgrade() -> None:
    op.drop_index("idx_messages_last_activity", table_name="messages")
    op.drop_column("messages", "last_activity_at")
