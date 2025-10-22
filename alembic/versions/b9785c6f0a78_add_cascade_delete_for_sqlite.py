"""add_cascade_delete_for_sqlite

Revision ID: b9785c6f0a78
Revises: 7e8e4839ff21
Create Date: 2025-09-28 14:55:44.187166

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import sqlite

# revision identifiers, used by Alembic.
revision: str = "b9785c6f0a78"
down_revision: Union[str, Sequence[str], None] = "7e8e4839ff21"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade():
    """SQLite-spezifische Migration für CASCADE DELETE."""

    # SQLite benötigt PRAGMA foreign_keys = ON
    connection = op.get_bind()

    # Prüfe ob es SQLite ist
    if connection.dialect.name == "sqlite":
        # SQLite: Table recreation strategy

        # 1. Foreign Keys temporär deaktivieren
        connection.execute(sa.text("PRAGMA foreign_keys = OFF"))

        # 2. Backup Tables erstellen
        connection.execute(
            sa.text("""
            CREATE TABLE votes_backup AS
            SELECT * FROM votes
        """)
        )

        connection.execute(
            sa.text("""
            CREATE TABLE poll_options_backup AS
            SELECT * FROM poll_options
        """)
        )

        # 3. Alte Tables löschen
        op.drop_table("votes")
        op.drop_table("poll_options")

        # 4. Neue Tables mit CASCADE erstellen
        op.create_table(
            "poll_options",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("text", sa.String(200), nullable=False),
            sa.Column("order_index", sa.Integer(), nullable=False),
            sa.Column("poll_id", sa.Integer(), nullable=False),
            sa.ForeignKeyConstraint(["poll_id"], ["polls.id"], ondelete="CASCADE"),
        )

        op.create_table(
            "votes",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column(
                "created_at", sa.DateTime(timezone=True), server_default=sa.func.now()
            ),
            sa.Column("user_id", sa.Integer(), nullable=False),
            sa.Column("poll_id", sa.Integer(), nullable=False),
            sa.Column("option_id", sa.Integer(), nullable=False),
            sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
            sa.ForeignKeyConstraint(["poll_id"], ["polls.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(
                ["option_id"], ["poll_options.id"], ondelete="CASCADE"
            ),
            sa.UniqueConstraint("poll_id", "user_id", name="uq_vote_poll_user"),
        )

        # 5. Daten zurück kopieren
        connection.execute(
            sa.text("""
            INSERT INTO poll_options (id, text, order_index, poll_id)
            SELECT id, text, order_index, poll_id
            FROM poll_options_backup
            WHERE poll_id IN (SELECT id FROM polls)
        """)
        )

        connection.execute(
            sa.text("""
            INSERT INTO votes (id, created_at, user_id, poll_id, option_id)
            SELECT v.id, v.created_at, v.user_id, v.poll_id, v.option_id
            FROM votes_backup v
            WHERE v.poll_id IN (SELECT id FROM polls)
            AND v.option_id IN (SELECT id FROM poll_options)
        """)
        )

        # 6. Backup Tables löschen
        connection.execute(sa.text("DROP TABLE votes_backup"))
        connection.execute(sa.text("DROP TABLE poll_options_backup"))

        # 7. Foreign Keys wieder aktivieren
        connection.execute(sa.text("PRAGMA foreign_keys = ON"))

    else:
        # PostgreSQL: Standard FK modification
        op.drop_constraint(
            "poll_options_poll_id_fkey", "poll_options", type_="foreignkey"
        )
        op.drop_constraint("votes_poll_id_fkey", "votes", type_="foreignkey")
        op.drop_constraint("votes_option_id_fkey", "votes", type_="foreignkey")

        op.create_foreign_key(
            "poll_options_poll_id_fkey",
            "poll_options",
            "polls",
            ["poll_id"],
            ["id"],
            ondelete="CASCADE",
        )
        op.create_foreign_key(
            "votes_poll_id_fkey",
            "votes",
            "polls",
            ["poll_id"],
            ["id"],
            ondelete="CASCADE",
        )
        op.create_foreign_key(
            "votes_option_id_fkey",
            "votes",
            "poll_options",
            ["option_id"],
            ["id"],
            ondelete="CASCADE",
        )

        op.create_unique_constraint(
            "uq_vote_poll_user", "votes", ["poll_id", "user_id"]
        )


def downgrade():
    """Rollback der CASCADE DELETE Migration."""
    connection = op.get_bind()

    if connection.dialect.name == "sqlite":
        # SQLite rollback - ähnliche Table recreation
        connection.execute(sa.text("PRAGMA foreign_keys = OFF"))

        # Backup erstellen
        connection.execute(sa.text("CREATE TABLE votes_backup AS SELECT * FROM votes"))
        connection.execute(
            sa.text("CREATE TABLE poll_options_backup AS SELECT * FROM poll_options")
        )

        # Tables neu erstellen ohne CASCADE
        op.drop_table("votes")
        op.drop_table("poll_options")

        op.create_table(
            "poll_options",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("text", sa.String(200), nullable=False),
            sa.Column("order_index", sa.Integer(), nullable=False),
            sa.Column("poll_id", sa.Integer(), nullable=False),
            sa.ForeignKeyConstraint(["poll_id"], ["polls.id"]),  # Ohne ondelete
        )

        op.create_table(
            "votes",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column(
                "created_at", sa.DateTime(timezone=True), server_default=sa.func.now()
            ),
            sa.Column("user_id", sa.Integer(), nullable=False),
            sa.Column("poll_id", sa.Integer(), nullable=False),
            sa.Column("option_id", sa.Integer(), nullable=False),
            sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
            sa.ForeignKeyConstraint(["poll_id"], ["polls.id"]),  # Ohne ondelete
            sa.ForeignKeyConstraint(
                ["option_id"], ["poll_options.id"]
            ),  # Ohne ondelete
        )

        # Daten zurück kopieren
        connection.execute(
            sa.text("INSERT INTO poll_options SELECT * FROM poll_options_backup")
        )
        connection.execute(
            sa.text(
                "INSERT INTO votes SELECT id, created_at, user_id, poll_id, option_id FROM votes_backup"
            )
        )

        # Cleanup
        connection.execute(sa.text("DROP TABLE votes_backup"))
        connection.execute(sa.text("DROP TABLE poll_options_backup"))
        connection.execute(sa.text("PRAGMA foreign_keys = ON"))

    else:
        # PostgreSQL rollback
        op.drop_constraint("uq_vote_poll_user", "votes", type_="unique")
        op.drop_constraint("votes_option_id_fkey", "votes", type_="foreignkey")
        op.drop_constraint("votes_poll_id_fkey", "votes", type_="foreignkey")
        op.drop_constraint(
            "poll_options_poll_id_fkey", "poll_options", type_="foreignkey"
        )

        op.create_foreign_key(
            "poll_options_poll_id_fkey", "poll_options", "polls", ["poll_id"], ["id"]
        )
        op.create_foreign_key(
            "votes_poll_id_fkey", "votes", "polls", ["poll_id"], ["id"]
        )
        op.create_foreign_key(
            "votes_option_id_fkey", "votes", "poll_options", ["option_id"], ["id"]
        )
