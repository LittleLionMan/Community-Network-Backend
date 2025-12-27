"""Replace categories with genres and topics

Revision ID: ec96c12c89e7
Revises: bb8d87edf11b
Create Date: 2025-12-27 17:45:23.902317
"""

from typing import Sequence, Union

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "ec96c12c89e7"
down_revision: Union[str, Sequence[str], None] = "bb8d87edf11b"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema - Add genres and topics, remove categories."""

    # Schritt 1: Spalten hinzufügen (nullable=True)
    op.add_column(
        "books",
        sa.Column("genres", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )
    op.add_column(
        "books",
        sa.Column("topics", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )

    # Schritt 2: Default-Werte setzen
    op.execute("UPDATE books SET genres = '[]'::jsonb WHERE genres IS NULL")
    op.execute("UPDATE books SET topics = '[]'::jsonb WHERE topics IS NULL")

    # Schritt 3: NOT NULL Constraint hinzufügen
    op.alter_column("books", "genres", nullable=False)
    op.alter_column("books", "topics", nullable=False)

    # Indizes erstellen
    op.create_index(
        "idx_books_genres_gin",
        "books",
        ["genres"],
        unique=False,
        postgresql_using="gin",
    )
    op.create_index(
        "idx_books_topics_gin",
        "books",
        ["topics"],
        unique=False,
        postgresql_using="gin",
    )

    # Categories entfernen
    op.drop_index(
        "idx_books_categories_gin", table_name="books", postgresql_using="gin"
    )
    op.drop_column("books", "categories")


def downgrade() -> None:
    """Downgrade schema - Restore categories, remove genres and topics."""

    # Categories wiederherstellen
    op.add_column(
        "books",
        sa.Column("categories", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )
    op.execute("UPDATE books SET categories = '[]'::jsonb WHERE categories IS NULL")
    op.alter_column("books", "categories", nullable=False)
    op.create_index(
        "idx_books_categories_gin",
        "books",
        ["categories"],
        unique=False,
        postgresql_using="gin",
    )

    # Genres und Topics entfernen
    op.drop_index("idx_books_topics_gin", table_name="books", postgresql_using="gin")
    op.drop_index("idx_books_genres_gin", table_name="books", postgresql_using="gin")
    op.drop_column("books", "topics")
    op.drop_column("books", "genres")
