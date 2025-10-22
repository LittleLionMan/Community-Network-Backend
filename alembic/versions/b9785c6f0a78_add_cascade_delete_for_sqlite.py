"""cascade delete threads

Revision ID: b9785c6f0a78
Revises: 7e8e4839ff21
Create Date: 2025-10-22 16:25:55.340401

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "b9785c6f0a78"
down_revision: Union[str, Sequence[str], None] = "7e8e4839ff21"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema - Add CASCADE delete for forum_posts."""
    connection = op.get_bind()

    if connection.dialect.name == "sqlite":
        # SQLite: Muss Tabelle neu erstellen
        connection.execute(sa.text("PRAGMA foreign_keys = OFF"))

        # Backup erstellen
        connection.execute(
            sa.text("""
            CREATE TABLE forum_posts_backup AS
            SELECT * FROM forum_posts
        """)
        )

        # Alte Tabelle löschen
        op.drop_table("forum_posts")

        # Neu erstellen mit CASCADE
        op.create_table(
            "forum_posts",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("content", sa.Text(), nullable=False),
            sa.Column(
                "created_at", sa.DateTime(timezone=True), server_default=sa.func.now()
            ),
            sa.Column("updated_at", sa.DateTime(timezone=True), onupdate=sa.func.now()),
            sa.Column("author_id", sa.Integer(), nullable=False),
            sa.Column("thread_id", sa.Integer(), nullable=False),
            sa.Column("quoted_post_id", sa.Integer(), nullable=True),
            sa.Column("mentioned_user_ids", sa.JSON(), nullable=True),
            sa.ForeignKeyConstraint(["author_id"], ["users.id"]),
            sa.ForeignKeyConstraint(
                ["thread_id"], ["forum_threads.id"], ondelete="CASCADE"
            ),
            sa.ForeignKeyConstraint(
                ["quoted_post_id"], ["forum_posts.id"], ondelete="SET NULL"
            ),
        )

        # Daten zurück kopieren
        connection.execute(
            sa.text("""
            INSERT INTO forum_posts
            SELECT * FROM forum_posts_backup
        """)
        )

        # Backup löschen
        connection.execute(sa.text("DROP TABLE forum_posts_backup"))
        connection.execute(sa.text("PRAGMA foreign_keys = ON"))

    else:
        # PostgreSQL: Constraint ändern
        op.drop_constraint(
            "forum_posts_thread_id_fkey", "forum_posts", type_="foreignkey"
        )
        op.create_foreign_key(
            "forum_posts_thread_id_fkey",
            "forum_posts",
            "forum_threads",
            ["thread_id"],
            ["id"],
            ondelete="CASCADE",
        )


def downgrade() -> None:
    """Downgrade schema - Remove CASCADE delete."""
    connection = op.get_bind()

    if connection.dialect.name == "sqlite":
        # SQLite rollback
        connection.execute(sa.text("PRAGMA foreign_keys = OFF"))

        connection.execute(
            sa.text("CREATE TABLE forum_posts_backup AS SELECT * FROM forum_posts")
        )
        op.drop_table("forum_posts")

        op.create_table(
            "forum_posts",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("content", sa.Text(), nullable=False),
            sa.Column(
                "created_at", sa.DateTime(timezone=True), server_default=sa.func.now()
            ),
            sa.Column("updated_at", sa.DateTime(timezone=True), onupdate=sa.func.now()),
            sa.Column("author_id", sa.Integer(), nullable=False),
            sa.Column("thread_id", sa.Integer(), nullable=False),
            sa.Column("quoted_post_id", sa.Integer(), nullable=True),
            sa.Column("mentioned_user_ids", sa.JSON(), nullable=True),
            sa.ForeignKeyConstraint(["author_id"], ["users.id"]),
            sa.ForeignKeyConstraint(
                ["thread_id"], ["forum_threads.id"]
            ),  # Ohne CASCADE
            sa.ForeignKeyConstraint(
                ["quoted_post_id"], ["forum_posts.id"], ondelete="SET NULL"
            ),
        )

        connection.execute(
            sa.text("INSERT INTO forum_posts SELECT * FROM forum_posts_backup")
        )
        connection.execute(sa.text("DROP TABLE forum_posts_backup"))
        connection.execute(sa.text("PRAGMA foreign_keys = ON"))

    else:
        # PostgreSQL rollback
        op.drop_constraint(
            "forum_posts_thread_id_fkey", "forum_posts", type_="foreignkey"
        )
        op.create_foreign_key(
            "forum_posts_thread_id_fkey",
            "forum_posts",
            "forum_threads",
            ["thread_id"],
            ["id"],  # Ohne ondelete
        )
