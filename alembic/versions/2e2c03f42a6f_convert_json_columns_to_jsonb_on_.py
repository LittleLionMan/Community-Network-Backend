"""convert json columns to jsonb on postgres

Revision ID: 2e2c03f42a6f
Revises: cef8123ee2c4
Create Date: 2025-12-16 16:52:20.242719

"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "2e2c03f42a6f"
down_revision: Union[str, Sequence[str], None] = "cef8123ee2c4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade():
    bind = op.get_bind()
    dialect = bind.dialect.name

    if dialect == "postgresql":
        # Konvertiere Spalten auf JSONB
        op.alter_column(
            "books",
            "authors",
            type_=postgresql.JSONB,
            postgresql_using="authors::jsonb",
        )
        op.alter_column(
            "books",
            "categories",
            type_=postgresql.JSONB,
            postgresql_using="categories::jsonb",
        )

        # GIN-Indizes erstellen
        op.create_index(
            "idx_books_authors_gin", "books", ["authors"], postgresql_using="gin"
        )
        op.create_index(
            "idx_books_categories_gin", "books", ["categories"], postgresql_using="gin"
        )
    else:
        # SQLite und andere: Spalten bleiben JSON, normale Indexe
        op.create_index("idx_books_authors", "books", ["authors"])
        op.create_index("idx_books_categories", "books", ["categories"])


def downgrade():
    bind = op.get_bind()
    dialect = bind.dialect.name

    if dialect == "postgresql":
        # Optional: Downgrade zurück zu JSON
        op.alter_column(
            "books", "authors", type_=sa.JSON, postgresql_using="authors::json"
        )
        op.alter_column(
            "books", "categories", type_=sa.JSON, postgresql_using="categories::json"
        )
        op.drop_index("idx_books_authors_gin", table_name="books")
        op.drop_index("idx_books_categories_gin", table_name="books")
    else:
        op.drop_index("idx_books_authors", table_name="books")
        op.drop_index("idx_books_categories", table_name="books")
