"""rename_to_exact_address_private

Revision ID: 0310fe5e6900
Revises: ff046572c3b9
Create Date: 2025-12-12 18:17:13.471122

"""

from typing import Sequence, Union

import sqlalchemy as sa
from sqlalchemy.dialects import sqlite

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0310fe5e6900"
down_revision: Union[str, Sequence[str], None] = "ff046572c3b9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade():
    conn = op.get_bind()
    dialect = conn.dialect.name

    if dialect == "postgresql":
        # PostgreSQL kann rename column
        op.alter_column(
            "users", "location_private", new_column_name="exact_address_private"
        )

    else:
        # SQLite: kein rename → neue Spalte + Daten kopieren
        op.add_column(
            "users",
            sa.Column(
                "exact_address_private",
                sa.Boolean(),
                server_default=sa.text("0"),
                nullable=False,
            ),
        )

        # Kopiere Werte aus location_private in die neue Spalte
        op.execute("""
            UPDATE users
            SET exact_address_private = COALESCE(location_private, 0)
        """)

        # (Optional) alte Spalte entfernen – SQLite braucht Table recreation
        # Der einfache Weg: wir lassen sie drin.
        #
        # Wenn du sie *wirklich* entfernen willst, sag Bescheid,
        # dann generiere ich dir eine vollständige Table-Rebuild-Migration.


def downgrade():
    conn = op.get_bind()
    dialect = conn.dialect.name

    if dialect == "postgresql":
        op.alter_column(
            "users", "exact_address_private", new_column_name="location_private"
        )

    else:
        # SQLite: Neue (alte) Spalte hinzufügen
        op.add_column(
            "users",
            sa.Column(
                "location_private",
                sa.Boolean(),
                server_default=sa.text("0"),
                nullable=False,
            ),
        )

        # Werte zurückkopieren
        op.execute("""
            UPDATE users
            SET location_private = COALESCE(exact_address_private, 0)
        """)
