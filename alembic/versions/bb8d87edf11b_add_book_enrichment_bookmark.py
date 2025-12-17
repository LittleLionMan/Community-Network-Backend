"""add book enrichment bookmark

Revision ID: bb8d87edf11b
Revises: 2e2c03f42a6f
Create Date: 2025-12-17 09:40:29.951198

"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "bb8d87edf11b"
down_revision: Union[str, Sequence[str], None] = "2e2c03f42a6f"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade():
    op.create_table(
        "book_enrichment_bookmarks",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("last_processed_book_id", sa.Integer(), nullable=True),
        sa.Column(
            "last_run_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("books_checked", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("books_updated", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("google_requests", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "openlibrary_requests", sa.Integer(), nullable=False, server_default="0"
        ),
        sa.Column(
            "status", sa.String(length=50), nullable=False, server_default="completed"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "idx_book_enrichment_last_run",
        "book_enrichment_bookmarks",
        ["last_run_at"],
        unique=False,
    )

    op.create_table(
        "book_last_checked",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("book_id", sa.Integer(), nullable=False),
        sa.Column(
            "last_checked_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["book_id"], ["books.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("book_id"),
    )
    op.create_index(
        "idx_book_last_checked_book_id", "book_last_checked", ["book_id"], unique=True
    )
    op.create_index(
        "idx_book_last_checked_date",
        "book_last_checked",
        ["last_checked_at"],
        unique=False,
    )


def downgrade():
    op.drop_index("idx_book_last_checked_date", table_name="book_last_checked")
    op.drop_index("idx_book_last_checked_book_id", table_name="book_last_checked")
    op.drop_table("book_last_checked")

    op.drop_index(
        "idx_book_enrichment_last_run", table_name="book_enrichment_bookmarks"
    )
    op.drop_table("book_enrichment_bookmarks")
