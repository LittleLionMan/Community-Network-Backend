"""Add exchange_transactions table

Revision ID: 630fa896e3bf
Revises: 1d7e07e63e50
Create Date: 2025-11-28 16:14:03.847728

"""

from typing import Sequence, Union

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "630fa896e3bf"
down_revision: Union[str, Sequence[str], None] = "1d7e07e63e50"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()
    dialect = conn.dialect.name

    if dialect == "postgresql":
        op.execute("""
            DO $$ BEGIN
                CREATE TYPE transactionstatus AS ENUM (
                    'pending', 'accepted', 'time_confirmed', 'completed',
                    'cancelled', 'rejected', 'expired'
                );
            EXCEPTION
                WHEN duplicate_object THEN null;
            END $$;
        """)

        op.execute("""
            DO $$ BEGIN
                CREATE TYPE transactiontype AS ENUM (
                    'book_exchange', 'service_meetup', 'event_confirmation'
                );
            EXCEPTION
                WHEN duplicate_object THEN null;
            END $$;
        """)

        status_col = sa.String(length=50)
        type_col = sa.String(length=50)
    else:
        status_col = sa.String(length=20)
        type_col = sa.String(length=30)

    op.create_table(
        "exchange_transactions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("message_id", sa.Integer(), nullable=False),
        sa.Column("transaction_type", type_col, nullable=False),
        sa.Column("offer_type", sa.String(length=30), nullable=False),
        sa.Column("offer_id", sa.Integer(), nullable=False),
        sa.Column("requester_id", sa.Integer(), nullable=False),
        sa.Column("provider_id", sa.Integer(), nullable=False),
        sa.Column("status", status_col, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("accepted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("time_confirmed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("proposed_times", sa.JSON(), nullable=False),
        sa.Column("confirmed_time", sa.DateTime(timezone=True), nullable=True),
        sa.Column("requester_confirmed_handover", sa.Boolean(), nullable=True),
        sa.Column("provider_confirmed_handover", sa.Boolean(), nullable=True),
        sa.Column("credit_amount", sa.Integer(), nullable=True),
        sa.Column("credit_transferred", sa.Boolean(), nullable=True),
        sa.Column("exact_address", sa.String(length=500), nullable=True),
        sa.Column("metadata", sa.JSON(), nullable=False),
        sa.ForeignKeyConstraint(["message_id"], ["messages.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["provider_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["requester_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("message_id"),
    )

    op.create_index("idx_transaction_message", "exchange_transactions", ["message_id"])
    op.create_index(
        "idx_transaction_offer", "exchange_transactions", ["offer_type", "offer_id"]
    )
    op.create_index(
        "idx_transaction_requester", "exchange_transactions", ["requester_id", "status"]
    )
    op.create_index(
        "idx_transaction_provider", "exchange_transactions", ["provider_id", "status"]
    )
    op.create_index("idx_transaction_status", "exchange_transactions", ["status"])
    op.create_index("idx_transaction_expires", "exchange_transactions", ["expires_at"])

    if dialect == "postgresql":
        op.execute("""
            ALTER TABLE exchange_transactions
            ALTER COLUMN status TYPE transactionstatus
            USING status::transactionstatus
        """)
        op.execute("""
            ALTER TABLE exchange_transactions
            ALTER COLUMN transaction_type TYPE transactiontype
            USING transaction_type::transactiontype
        """)

    with op.batch_alter_table("messages", schema=None) as batch_op:
        batch_op.add_column(sa.Column("transaction_data", sa.JSON(), nullable=True))


def downgrade() -> None:
    conn = op.get_bind()
    dialect = conn.dialect.name

    with op.batch_alter_table("messages", schema=None) as batch_op:
        batch_op.drop_column("transaction_data")

    op.drop_index("idx_transaction_expires", table_name="exchange_transactions")
    op.drop_index("idx_transaction_status", table_name="exchange_transactions")
    op.drop_index("idx_transaction_provider", table_name="exchange_transactions")
    op.drop_index("idx_transaction_requester", table_name="exchange_transactions")
    op.drop_index("idx_transaction_offer", table_name="exchange_transactions")
    op.drop_index("idx_transaction_message", table_name="exchange_transactions")

    op.drop_table("exchange_transactions")

    if dialect == "postgresql":
        sa.Enum(name="transactiontype").drop(conn, checkfirst=True)
        sa.Enum(name="transactionstatus").drop(conn, checkfirst=True)
