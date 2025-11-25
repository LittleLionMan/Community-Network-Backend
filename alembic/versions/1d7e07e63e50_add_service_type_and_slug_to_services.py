"""Add service_type and slug to services

Revision ID: 1d7e07e63e50
Revises: e1a2b3c4d5e6
Create Date: 2025-11-25 18:40:50.676003

"""

from typing import Sequence, Union

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "1d7e07e63e50"
down_revision: Union[str, Sequence[str], None] = "e1a2b3c4d5e6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()
    dialect = conn.dialect.name

    # Enum für PostgreSQL erstellen
    if dialect == "postgresql":
        service_type_enum = postgresql.ENUM(
            "user_service",
            "platform_feature",
            name="servicetype",
            create_type=True,
        )
        service_type_enum.create(conn, checkfirst=True)
        service_type_col = sa.Enum(
            "user_service",
            "platform_feature",
            name="servicetype",
            native_enum=True,
        )
    else:
        service_type_col = sa.String(length=20)

    with op.batch_alter_table("services", schema=None) as batch_op:
        batch_op.add_column(sa.Column("service_type", service_type_col, nullable=True))
        batch_op.add_column(sa.Column("slug", sa.String(length=100), nullable=True))

    # ✅ WICHTIG: Bestehende Services zu USER_SERVICE konvertieren
    if dialect == "postgresql":
        op.execute(
            "UPDATE services SET service_type = 'user_service' WHERE service_type IS NULL"
        )
    else:
        # SQLite
        op.execute(
            "UPDATE services SET service_type = 'user_service' WHERE service_type IS NULL OR service_type = ''"
        )

    # Jetzt service_type als NOT NULL setzen mit Default
    with op.batch_alter_table("services", schema=None) as batch_op:
        if dialect == "postgresql":
            batch_op.alter_column(
                "service_type",
                existing_type=service_type_col,
                nullable=False,
                server_default="user_service",
            )
        else:
            # SQLite: batch_alter_table macht das automatisch
            # Aber wir müssen sicherstellen, dass alle Werte gesetzt sind
            pass

    # Indizes erstellen
    op.create_index("ix_services_slug", "services", ["slug"], unique=True)
    op.create_index("ix_services_service_type", "services", ["service_type"])

    if dialect == "postgresql":
        op.create_index(
            "idx_services_type_active",
            "services",
            ["service_type", "is_active"],
        )
    else:
        op.execute(
            "CREATE INDEX IF NOT EXISTS idx_services_type_active ON services (service_type, is_active)"
        )


def downgrade() -> None:
    conn = op.get_bind()
    dialect = conn.dialect.name

    # Indizes löschen
    if dialect == "sqlite":
        op.execute("DROP INDEX IF EXISTS idx_services_type_active")
    else:
        op.drop_index("idx_services_type_active", table_name="services")

    op.drop_index("ix_services_service_type", table_name="services")
    op.drop_index("ix_services_slug", table_name="services")

    # Spalten löschen
    with op.batch_alter_table("services", schema=None) as batch_op:
        batch_op.drop_column("slug")
        batch_op.drop_column("service_type")

    # Enum für PostgreSQL löschen
    if dialect == "postgresql":
        sa.Enum(name="servicetype").drop(conn, checkfirst=True)
