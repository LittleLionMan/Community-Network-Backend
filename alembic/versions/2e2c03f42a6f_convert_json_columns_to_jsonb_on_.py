"""convert json columns to jsonb on postgres

Revision ID: 2e2c03f42a6f
Revises: cef8123ee2c4
Create Date: 2025-12-16 16:52:20.242719

"""

from typing import Sequence, Union

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

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
        pass
    else:
        op.create_index("idx_books_authors", "books", ["authors"])
        op.create_index("idx_books_categories", "books", ["categories"])


def downgrade():
    bind = op.get_bind()
    dialect = bind.dialect.name

    if dialect == "postgresql":
        pass
    else:
        op.drop_index("idx_books_authors", table_name="books")
        op.drop_index("idx_books_categories", table_name="books")
