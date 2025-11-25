"""Add books and geodata

Revision ID: e1a2b3c4d5e6
Revises: 64c913c72853
Create Date: 2025-11-25 14:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "e1a2b3c4d5e6"
down_revision: Union[str, Sequence[str], None] = "64c913c72853"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()
    dialect = conn.dialect.name

    with op.batch_alter_table("users", schema=None) as batch_op:
        batch_op.add_column(sa.Column("location_lat", sa.Float(), nullable=True))
        batch_op.add_column(sa.Column("location_lon", sa.Float(), nullable=True))
        batch_op.add_column(
            sa.Column("location_geocoded_at", sa.DateTime(timezone=True), nullable=True)
        )
        batch_op.add_column(
            sa.Column("location_district", sa.String(length=200), nullable=True)
        )
        batch_op.add_column(
            sa.Column(
                "book_credits_remaining",
                sa.Integer(),
                nullable=False,
                server_default="1",
            )
        )
        batch_op.add_column(
            sa.Column(
                "book_credits_last_reset", sa.DateTime(timezone=True), nullable=True
            )
        )

        if dialect == "postgresql":
            batch_op.create_index(
                "idx_user_location_coords", ["location_lat", "location_lon"]
            )

    if dialect == "sqlite":
        op.execute(
            "CREATE INDEX IF NOT EXISTS idx_user_location_coords ON users (location_lat, location_lon)"
        )

    op.create_table(
        "books",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("title", sa.String(length=300), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("cover_image_url", sa.String(length=500), nullable=True),
        sa.Column("thumbnail_url", sa.String(length=500), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column("isbn_13", sa.String(length=13), nullable=False, unique=True),
        sa.Column("isbn_10", sa.String(length=10), nullable=True),
        sa.Column(
            "authors",
            sa.JSON() if dialect == "postgresql" else sa.Text(),
            nullable=False,
        ),
        sa.Column("publisher", sa.String(length=200), nullable=True),
        sa.Column("published_date", sa.String(length=50), nullable=True),
        sa.Column(
            "language", sa.String(length=10), nullable=False, server_default="de"
        ),
        sa.Column("page_count", sa.Integer(), nullable=True),
        sa.Column(
            "categories",
            sa.JSON() if dialect == "postgresql" else sa.Text(),
            nullable=False,
        ),
    )

    op.create_index("idx_books_isbn_13", "books", ["isbn_13"], unique=True)
    op.create_index("idx_books_isbn_10", "books", ["isbn_10"])
    op.create_index("idx_books_title", "books", ["title"])

    if dialect == "postgresql":
        op.create_index(
            "idx_books_authors_gin", "books", ["authors"], postgresql_using="gin"
        )
        op.create_index(
            "idx_books_categories_gin", "books", ["categories"], postgresql_using="gin"
        )

    if dialect == "postgresql":
        book_condition_enum = postgresql.ENUM(
            "new",
            "like_new",
            "good",
            "acceptable",
            name="bookcondition",
            create_type=True,
        )
        book_condition_enum.create(conn, checkfirst=True)
        condition_type = sa.Enum(
            "new",
            "like_new",
            "good",
            "acceptable",
            name="bookcondition",
            native_enum=True,
        )
    else:
        condition_type = sa.String(length=20)

    op.create_table(
        "book_offers",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("location_lat", sa.Float(), nullable=True),
        sa.Column("location_lon", sa.Float(), nullable=True),
        sa.Column("location_district", sa.String(length=200), nullable=True),
        sa.Column("is_available", sa.Boolean(), nullable=False, server_default="1"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("book_id", sa.Integer(), nullable=False),
        sa.Column("owner_id", sa.Integer(), nullable=False),
        sa.Column("condition", condition_type, nullable=False),
        sa.Column("user_comment", sa.Text(), nullable=True),
        sa.Column("custom_cover_image_url", sa.String(length=500), nullable=True),
        sa.Column("reserved_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("reserved_by_user_id", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(["book_id"], ["books.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["owner_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["reserved_by_user_id"], ["users.id"], ondelete="SET NULL"
        ),
    )

    op.create_index("idx_book_offers_owner", "book_offers", ["owner_id"])
    op.create_index(
        "idx_book_offers_location_coords",
        "book_offers",
        ["location_lat", "location_lon"],
    )
    op.create_index("idx_book_offers_book", "book_offers", ["book_id"])
    op.create_index("idx_book_offers_created", "book_offers", ["created_at"])
    op.create_index("idx_book_offers_available", "book_offers", ["is_available"])


def downgrade() -> None:
    conn = op.get_bind()
    dialect = conn.dialect.name

    op.drop_index("idx_book_offers_available", table_name="book_offers")
    op.drop_index("idx_book_offers_created", table_name="book_offers")
    op.drop_index("idx_book_offers_book", table_name="book_offers")
    op.drop_index("idx_book_offers_location_coords", table_name="book_offers")
    op.drop_index("idx_book_offers_owner", table_name="book_offers")
    op.drop_table("book_offers")

    if dialect == "postgresql":
        sa.Enum(name="bookcondition").drop(conn, checkfirst=True)

    if dialect == "postgresql":
        op.drop_index("idx_books_categories_gin", table_name="books")
        op.drop_index("idx_books_authors_gin", table_name="books")

    op.drop_index("idx_books_title", table_name="books")
    op.drop_index("idx_books_isbn_10", table_name="books")
    op.drop_index("idx_books_isbn_13", table_name="books")
    op.drop_table("books")

    with op.batch_alter_table("users", schema=None) as batch_op:
        batch_op.drop_column("book_credits_last_reset")
        batch_op.drop_column("book_credits_remaining")
        batch_op.drop_column("location_district")
        batch_op.drop_column("location_geocoded_at")
        batch_op.drop_column("location_lon")
        batch_op.drop_column("location_lat")

        if dialect == "postgresql":
            batch_op.drop_index("idx_user_location_coords")

    if dialect == "sqlite":
        op.execute("DROP INDEX IF EXISTS idx_user_location_coords")
